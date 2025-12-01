from pathlib import Path
import re


APP_NAME = "My Player"

# App window size
APP_WINDOW_WIDTH = 1300
APP_WINDOW_HEIGHT = 760

# Data directories
APP_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR        = APP_ROOT / "data"
LIBRARY_DIR     = DATA_DIR / "library"
SONGS_DIR       = DATA_DIR / "songs"
AI_DIR          = APP_ROOT / "ai"
AI_MODELS_DIR   = AI_DIR / "models"
AI_DATA_DIR     = AI_DIR / "data"

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
    "no_playlist": True,
    "quiet": True,
    "no_warnings": True,
    "audio_format": "mp3"
}
# song length to be valid for download
MIN_SEC = 150
MAX_SEC = 540

# YouTube song search filters
YOUTUBE_SEARCH_FILTERS = ["Official Audio", "Audio", "Lyric Video", "Lyrics", "Full Song"]
BAD_SEARCH_KEYWORDS = [
    'interview', 'cover', '8d', 'stage', 'remix', 'status', 'reaction', 'behind the scenes',
    'podcast', 'karaoke', 'making of', 'speed up', 'movie', 'unplugged', 'jukebox', 'performance',
    'album jukebox', 'video jukebox', 'shorts', 'ringtone', 'cover by', 'promo', 'saregama carvaan',
    'live', 'full album', 'audio jukebox', 'slowed', 'lofi', 'caller tune', 'teaser', 'reprise', 'trailer'
]
OFFICIAL_YOUTUBE_CHANNELS = ["t-series", "saregama", "sony", "saregama music", "zee music", "tips official", "svf", "svf music"]

# How many rows to populate per timer “batch”
TABLE_BATCH_SIZE = 10  # how many songs load at a time. Smaller value means better app responsiveness
PREFETCH_MS = 60_000

# AI Model
RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
RERANKER_MODEL_DIR = AI_MODELS_DIR / "songlink_reranker"

# AI Dataset + Training Config
SONGLINK_RAW_DATASET    = AI_DATA_DIR / "songlink_train_raw.csv"
SONGLINK_TRAIN_DATASET  = AI_DATA_DIR / "songlink_train.csv"  # final curated or synthetic dataset
SONGLINK_QUERIES_TXT    = AI_DATA_DIR / "queries.txt"

YTDP_LIMIT_PER_QUERY    = 10      # number of search results per query
RERANKER_EPOCHS         = 2
RERANKER_BATCH_SIZE     = 16
RERANKER_TEST_SPLIT     = 0.1     # train/validation split

# AI Auto-train settings
TRAINING_META_FILE = RERANKER_MODEL_DIR / "training_meta.json"
MIN_NEW_SAMPLES_FOR_RETRAIN = 10  # train only if dataset grew by at least this many samples
TRAINING_SEQUENCE_LENGTH = 445  # max tokens for CrossEncoder input sequences
