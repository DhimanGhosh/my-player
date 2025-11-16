from typing import Optional, Dict

from my_player.models.song import Song
from my_player.helpers.file_utils import resolve_existing_file


def sec_from_cache_val(val) -> Optional[int]:
    """Return duration in seconds from mixed cache (seconds or milliseconds)."""
    try:
        v = int(val)
    except Exception:
        return None

    # If value looks like milliseconds (>= 60,000) and converts to a plausible length (<12h), use ms→s.
    if v >= 60_000:
        v2 = v // 1000
        if 0 < v2 < 12 * 3600:
            return v2

    # If already seconds but implausibly huge (>12h), ignore.
    if v <= 0 or v >= 12 * 3600:
        return None

    return v


def cached_seconds(duration_db: Dict[str, int], s: Song) -> Optional[int]:
    """Return cached seconds for a song, checking both song-key and file-path keys."""
    try:
        k1 = "|".join(s.key())
        if k1 in duration_db:
            sec = sec_from_cache_val(duration_db[k1])
            if sec is not None:
                return sec
        p = resolve_existing_file(s, migrate=True)
        sp = str(p)
        if sp in duration_db:
            sec = sec_from_cache_val(duration_db[sp])
            if sec is not None:
                return sec
    except Exception:
        pass
    return None


def mmss_from_seconds(sec: int) -> str:
    m = max(0, sec) // 60
    s = max(0, sec) % 60
    return f"{m:02d}:{s:02d}"


def ms_to_mmss(ms: int) -> str:
    ms = max(0, int(ms))
    s = ms // 1000
    m = s // 60
    s = s % 60
    return f"{m:02d}:{s:02d}"
