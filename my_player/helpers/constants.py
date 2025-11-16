from pathlib import Path
import re


APP_NAME = "My Player"

# App window size
APP_WINDOW_WIDTH = 1300
APP_WINDOW_HEIGHT = 760

# Data directories
APP_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR    = APP_ROOT / "data"
LIBRARY_DIR = DATA_DIR / "library"
SONGS_DIR   = DATA_DIR / "songs"

CACHE_DIR        = APP_ROOT / "data" / "cache"
STATE_DB         = CACHE_DIR / ".player_state.json"
DURATION_DB      = CACHE_DIR / ".durations_cache.json"
HISTORY_DB       = CACHE_DIR / ".listening_history.json"
CUSTOM_SOURCE_DB = CACHE_DIR / ".custom_sources.json"

# Ensure directories exist
for _d in (DATA_DIR, SONGS_DIR, LIBRARY_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# Allowed characters for filenames
SAFE_CHAR_RE = re.compile(r"[^A-Za-z0-9._\- ]+")

# Default search scope
SEARCH_SCOPE_CATEGORY = "Category"
SEARCH_SCOPE_GLOBAL = "Global"

SPECIAL_FAV_CATEGORY = "[FAVOURITES]"
SPECIAL_PL_CATEGORY_PREFIX = "[Playlist]"

# yt_dlp configs
YTDLP_DEFAULT_ARGS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
}
YTDLP_PROGRESS_HOOK_KEY = "progress_hooks"

# YouTube song search filters
YOUTUBE_SEARCH_FILTERS = [
    "Official Audio",
    "Audio",
    "Lyric Video",
    "Lyrics",
    "Full Song",
]
BAD_SEARCH_KEYWORDS = [
    "jukebox","full album","album jukebox","audio jukebox","podcast","reaction","interview",
    "teaser","trailer","live","stage","performance","remix","reprise","lofi","cover","cover by",
    "unplugged","karaoke","8d","speed up","slowed","movie","lofi"
]

# song length to be valid for download
MIN_SEC = 150
MAX_SEC = 540

# How many rows to populate per timer “batch”
TABLE_BATCH_SIZE = 10  # how many songs load at a time. Smaller value means better app responsiveness
PREFETCH_MS = 60_000
