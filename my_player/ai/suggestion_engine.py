import json
import subprocess
import sys
import time
from collections import Counter
from typing import Dict, List, Tuple, Optional, Set

from my_player.models.song import Song
from my_player.ai.songlink_reranker import pick_best_candidate
from my_player.models.history_suggestion import HistoryInfo


class SuggestionEngine:
    """
    AI-driven suggestion engine.

    Responsibilities:
      - Learn from local play history (plays + recency).
      - Produce a sorted list of local suggestions.
      - Derive a "listening profile" (top artists / languages).
      - Use that profile + AI reranker to propose NEW songs from YouTube
        that match the frequently played artists / languages.

    This is intentionally pure Python; the "AI" part is delegated to:
      - my_player.ai.songlink_reranker.pick_best_candidate
        (CrossEncoder / finetuned reranker, with heuristics fallback)
      - plus pattern learning from history.
    """

    def __init__(self, history: Dict[str, dict], all_songs: List[Song]) -> None:
        self.history_raw = history or {}
        self.all_songs = all_songs or []

        # Map key string -> Song for easy lookups
        self._song_by_key_str: Dict[str, Song] = {}
        for s in self.all_songs:
            # Assuming Song.key() returns (category, title, album, artists_str) or similar
            key_str = "||".join(s.key())  # type: ignore[attr-defined]
            self._song_by_key_str[key_str] = s

        self._now = time.time()

    # ------------------------------------------------------------------
    # 1) Local suggestions (most played + recency)
    # ------------------------------------------------------------------

    def _history_info(self, key_str: str, info: dict) -> HistoryInfo:
        try:
            plays = float(info.get("plays", 0))
        except Exception:
            plays = 0.0

        try:
            last_ts = float(info.get("last_played_ts", 0.0))
        except Exception:
            last_ts = 0.0

        return HistoryInfo(plays=plays, last_ts=last_ts)

    def _score_local(self, h: HistoryInfo) -> float:
        # Recency: more recent -> closer to 1.0
        if h.last_ts > 0:
            days_ago = max((self._now - h.last_ts) / 86400.0, 0.0)
            recency = 1.0 / (1.0 + days_ago)  # decays over time
        else:
            recency = 0.0

        # Score: 70% plays, 30% recency-weighted plays
        return h.plays * 0.7 + h.plays * recency * 0.3

    def build_local_suggestions(self, limit: int = 200) -> List[Song]:
        """
        Return local songs sorted by a score that combines plays + recency.
        """
        scored: List[Tuple[float, Song]] = []

        for key_str, info in self.history_raw.items():
            h = self._history_info(key_str, info)
            if h.plays <= 0 and h.last_ts <= 0:
                continue

            song = self._song_by_key_str.get(key_str)
            if song is None:
                continue

            score = self._score_local(h)
            scored.append((score, song))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [s for _, s in scored[:limit]]

    # ------------------------------------------------------------------
    # 2) Listening profile from local usage
    # ------------------------------------------------------------------

    def _build_listening_profile(self, base_songs: List[Song]) -> Tuple[List[str], List[str]]:
        """
        From the most-played songs, derive:
          - top artists
          - top "language" / category labels (we treat Song.category as language/cluster)
        """
        artist_counter: Counter[str] = Counter()
        lang_counter: Counter[str] = Counter()

        # Map for quick play counts per key
        plays_by_key: Dict[str, float] = {}
        for key_str, info in self.history_raw.items():
            h = self._history_info(key_str, info)
            plays_by_key[key_str] = h.plays

        for s in base_songs:
            key_str = "||".join(s.key())  # type: ignore[attr-defined]
            plays = plays_by_key.get(key_str, 1.0)

            # Artists
            for a in s.artists:  # type: ignore[attr-defined]
                name = (a or "").strip()
                if not name:
                    continue
                artist_counter[name] += plays

            # Languages / categories: treat Song.category as a proxy
            cat = getattr(s, "category", "") or ""
            cat = cat.strip()
            if cat:
                lang_counter[cat] += plays

        top_artists = [a for a, _ in artist_counter.most_common(5)]
        top_langs = [l for l, _ in lang_counter.most_common(5)]

        return top_artists, top_langs

    # ------------------------------------------------------------------
    # 3) External suggestions (new songs from the internet)
    # ------------------------------------------------------------------

    def _search_youtube_candidates(self, query: str, limit: int = 10) -> List[dict]:
        """
        Use yt-dlp in JSON mode to fetch top N YouTube search candidates
        for the given query. Returns a list of dicts compatible with
        pick_best_candidate().
        """
        if not query:
            return []

        cmd = [
            sys.executable,
            "-m",
            "yt_dlp",
            "-j",
            f"ytsearch{limit}:{query}",
            "--no-playlist",
        ]

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except Exception:
            return []

        if proc.returncode != 0:
            return []

        candidates: List[dict] = []
        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                info = json.loads(line)
            except Exception:
                continue

            url = info.get("webpage_url") or info.get("url")
            title = info.get("title")
            if not url or not title:
                continue

            candidates.append(
                {
                    "url": url,
                    "title": title,
                    "description": info.get("description") or "",
                    "channel": info.get("channel") or "",
                    "duration": info.get("duration") or 0,
                }
            )

        return candidates

    def _existing_title_artist_pairs(self) -> Set[Tuple[str, str]]:
        pairs: Set[Tuple[str, str]] = set()
        for s in self.all_songs:
            title = (s.title or "").strip().lower()  # type: ignore[attr-defined]
            for a in s.artists:  # type: ignore[attr-defined]
                artist = (a or "").strip().lower()
                if title and artist:
                    pairs.add((title, artist))
        return pairs

    def build_external_suggestions(self, max_external: int = 50) -> List[Song]:
        """
        Suggest NEW songs from YouTube that match the genre / artist / language
        patterns of the songs played most.

        Steps:
          - Take top local suggestions.
          - Build a listening profile (top artists + languages).
          - For each top artist (and optionally language), build
            smart YouTube search queries (full song / audio).
          - Use songlink_reranker.pick_best_candidate (finetuned model if present)
            to pick the best result.
          - Create transient Song objects in a special category
            "AI Suggestions (Online)" so they work with the existing
            download + playback pipeline.
        """
        # Seed from local favorites
        local_seed = self.build_local_suggestions(limit=100)
        if not local_seed:
            return []

        top_artists, top_langs = self._build_listening_profile(local_seed)
        if not top_artists:
            return []

        existing_pairs = self._existing_title_artist_pairs()

        suggestions: List[Song] = []
        seen_urls: Set[str] = set()

        # Build a few queries per top artist
        queries: List[Tuple[str, Optional[str]]] = []
        for artist in top_artists:
            # Attach most common language if we have one
            lang_hint = top_langs[0] if top_langs else None

            base = f"{artist} full song audio"
            queries.append((base, artist))

            # Slight variations
            if lang_hint:
                queries.append((f"{lang_hint} songs {artist} full song", artist))
            queries.append((f"{artist} best songs full video", artist))

        for query, artist_for_query in queries:
            if len(suggestions) >= max_external:
                break

            candidates = self._search_youtube_candidates(query, limit=8)
            if not candidates:
                continue

            best = pick_best_candidate(query, candidates)
            if not best:
                continue

            url = best.get("url", "").strip()
            title = (best.get("title", "") or "").strip()
            channel = (best.get("channel", "") or "").strip()
            if not url or not title:
                continue

            # Avoid duplicates: already in library
            pair_key = (title.lower(), (artist_for_query or "").lower())
            if pair_key in existing_pairs:
                continue

            if url in seen_urls:
                continue

            seen_urls.add(url)

            # Create a transient Song that can be used by the existing
            # download pipeline. We mark category as a special one.
            artists: List[str] = []
            if artist_for_query:
                artists.append(artist_for_query)
            elif channel:
                artists.append(channel)

            # Fallback channel as album hint
            album = channel or ""

            s = Song(
                title=title,
                album=album,
                artists=artists,
                category="AI Suggestions (Online)",
            )
            suggestions.append(s)

        return suggestions[:max_external]
