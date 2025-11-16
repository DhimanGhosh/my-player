from dataclasses import dataclass

from my_player.models.song import Song


@dataclass
class DownloadRequest:
    song: Song
    category: str
    source: str  # yt url or search string
    high: bool   # True for immediate priority


@dataclass
class DownloadJob:
    song: Song
    refresh: bool  # True = re-download even if file exists
    high: bool     # high-priority (play/prefetch), else bg
