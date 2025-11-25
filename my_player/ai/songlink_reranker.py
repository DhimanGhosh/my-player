from typing import List, Optional, Dict, Any

from my_player.models.yt_candidate import YTCandidate
from my_player.helpers.constants import (
    RERANKER_MODEL_DIR, BAD_SEARCH_KEYWORDS, OFFICIAL_YOUTUBE_CHANNELS
)

try:
    # Optional dependency; if not installed, we fall back to heuristics
    from sentence_transformers import CrossEncoder  # type: ignore
except Exception:  # pragma: no cover
    CrossEncoder = None  # type: ignore


_MODEL: Optional["CrossEncoder"] = None
_MODEL_LOADED: bool = False


def _load_model() -> Optional["CrossEncoder"]:
    """
    Lazy-load the CrossEncoder reranker from ai/models/songlink_reranker.
    If anything fails, returns None, and we will use heuristics.
    """
    global _MODEL, _MODEL_LOADED

    if _MODEL_LOADED:
        return _MODEL

    _MODEL_LOADED = True
    if CrossEncoder is None:
        return None

    model_dir = RERANKER_MODEL_DIR
    if not model_dir.exists():
        return None

    try:
        _MODEL = CrossEncoder(str(model_dir))
    except Exception:
        _MODEL = None

    return _MODEL


def _heuristic_score(query: str, c: YTCandidate) -> float:
    """
    Fallback scoring without an ML model:
    - Reward exact/partial matches for title, artists, album.
    - Penalize 'jukebox', 'carvaan', 'full album', trailers, etc.
    - Reward durations that look like a typical full song.
    """
    q = query.lower()

    title = c.title.lower()
    desc = (c.description or "").lower()
    channel = (c.channel or "").lower()

    score = 0.0

    # Basic overlap
    for token in q.split():
        if token and token in title:
            score += 2.0
        elif token and token in desc:
            score += 1.0

    # Prefer official or music label channels
    if any(k in channel for k in OFFICIAL_YOUTUBE_CHANNELS):
        score += 4.0

    # Penalize bad patterns
    if any(b in title or b in desc for b in BAD_SEARCH_KEYWORDS):
        score -= 8.0

    # Duration heuristic: prefer 2–9 minutes
    if c.duration:
        if 120 <= c.duration <= 540:
            score += 3.0
        elif c.duration < 60:
            score -= 4.0
        elif c.duration > 900:
            score -= 2.0

    return score


def pick_best_candidate(query: str, candidates: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Given a query string and a list of YT candidates (dicts with url, title, description,
    channel, duration), return the best candidate.

    If a finetuned CrossEncoder model is available under ai/models/songlink_reranker,
    use it; otherwise use heuristics.
    """
    if not candidates:
        return None

    # Normalize candidates
    norm_cands: List[YTCandidate] = []
    for c in candidates:
        url = str(c.get("url") or c.get("webpage_url") or "").strip()
        title = str(c.get("title") or "").strip()
        desc = str(c.get("description") or "").strip()
        channel = str(c.get("channel") or "").strip()
        duration = int(c.get("duration") or 0)
        if not url or not title:
            continue
        norm_cands.append(
            YTCandidate(
                url=url,
                title=title,
                description=desc,
                channel=channel,
                duration=duration,
            )
        )

    if not norm_cands:
        return None

    model = _load_model()

    if model is None:
        # Heuristic fallback
        scored = [( _heuristic_score(query, c), c ) for c in norm_cands]
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]
        return {
            "url": best.url,
            "title": best.title,
            "description": best.description,
            "channel": best.channel,
            "duration": best.duration,
        }

    # ML reranker: build (query, document) pairs
    pairs = []
    for c in norm_cands:
        doc = (
            f"Title: {c.title}\n"
            f"Channel: {c.channel}\n"
            f"Description: {c.description}\n"
            f"Duration: {c.duration} seconds"
        )
        pairs.append((query, doc))

    try:
        scores = model.predict(pairs)
    except Exception:
        # Fall back if model.predict fails
        scored = [( _heuristic_score(query, c), c ) for c in norm_cands]
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]
        return {
            "url": best.url,
            "title": best.title,
            "description": best.description,
            "channel": best.channel,
            "duration": best.duration,
        }

    # Pick best
    best_idx = int(max(range(len(scores)), key=lambda i: scores[i]))
    best = norm_cands[best_idx]
    return {
        "url": best.url,
        "title": best.title,
        "description": best.description,
        "channel": best.channel,
        "duration": best.duration,
        "score": float(scores[best_idx]),
    }
