from dataclasses import dataclass
from typing import List, Tuple, Dict

from my_player.helpers.file_utils import safe_filename
from my_player.helpers.utils import norm
from my_player.helpers.constants import YOUTUBE_SEARCH_FILTERS


@dataclass
class Song:
    category: str
    title: str
    album: str
    artists: List[str]

    def key(self) -> Tuple[str, str, str, str]:
        """
        Return a canonical key for this song used in history, playlists, etc.
        """
        return (
            self.category,
            self.title,
            self.album,
            ", ".join(self.artists),
        )

    def query_variants(self) -> List[str]:
        """
        Return multiple text variants to try when searching on YouTube.
        """
        artist_str = ", ".join(self.artists) if self.artists else ""
        base = f"{self.title} {artist_str}".strip()

        variants = [base]

        # Extended variants using YOUTUBE_SEARCH_FILTERS
        for kw in YOUTUBE_SEARCH_FILTERS:
            variants.append(f"{base} {kw}")
            if self.album:
                variants.append(f"{base} {self.album} {kw}")

        # Clean up + dedupe
        seen = set()
        out = []
        for s in variants:
            t = " ".join(s.split())
            if t and t not in seen:
                seen.add(t)
                out.append(norm(t))

        return out

    def out_filename(self) -> str:
        artist_str = ", ".join(self.artists) if self.artists else ""
        base = f"{self.title}"
        if artist_str:
            base += f" - {artist_str}"
        return safe_filename(base) + ".mp3"


def key_to_dict(key: Tuple[str, str, str, str]) -> Dict[str, str]:
    c, t, a, r = key
    return {"category": c, "title": t, "album": a, "artists": r}


def dict_to_key(d: Dict[str, str]) -> Tuple[str, str, str, str]:
    return (
        d.get("category", ""),
        d.get("title", ""),
        d.get("album", ""),
        d.get("artists", ""),
    )
