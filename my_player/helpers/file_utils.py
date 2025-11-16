from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

from my_player.helpers.constants import SAFE_CHAR_RE, SONGS_DIR

if TYPE_CHECKING:
    # Only for type checking – avoids runtime circular import
    from my_player.models.song import Song

# Very unsafe filesystem characters
_invalid_fs_chars = r'[<>:"/\\|?*\x00-\x1F]'
_invalid_fs_re = re.compile(_invalid_fs_chars)


def delete_part_files() -> int:
    """
    Recursively delete all *.part files under SONGS_DIR.

    Returns:
        Number of files deleted.
    """
    # TODO: use this as a separate background thread operation for regular cleanup of part files
    deleted_count = 0

    if not SONGS_DIR.exists():
        return 0

    for dir_path, _, files in os.walk(str(SONGS_DIR)):
        for file_name in files:
            if file_name.endswith(".part"):
                full_path = os.path.join(dir_path, file_name)
                try:
                    os.remove(full_path)
                    deleted_count += 1
                    print(f"Deleted: {full_path}")
                except OSError as e:
                    print(f"Failed to delete {full_path}: {e}")

    print(f"Total .part files deleted: {deleted_count}")
    return deleted_count


def safe_filename(name: str) -> str:
    """
    Make a reasonably safe filename fragment from an arbitrary string.

    - Strip leading/trailing whitespace.
    - Replace '/', '\\', ':' with '-'.
    - Apply SAFE_CHAR_RE from constants.
    - Guard against control chars and very unsafe FS chars.
    - Collapse repeated spaces/underscores.
    """
    name = name.strip().replace("/", "-").replace("\\", "-").replace(":", "-")
    name = SAFE_CHAR_RE.sub("_", name)
    name = _invalid_fs_re.sub("_", name)
    # Collapse repeats
    name = re.sub(r"[_\s]{2,}", " ", name)
    return name.strip()


def _sanitize_filename(s: str, replace_with: str = "_") -> str:
    """
    Internal helper used for constructing filenames.

    Uses a stricter sanitisation than safe_filename, but the core
    behaviour is consistent with your original libio_compat.py logic.
    """
    s = s.strip()
    # First apply SAFE_CHAR_RE rules
    s = SAFE_CHAR_RE.sub(replace_with, s)
    # Then enforce filesystem-invalid characters rule
    s = _invalid_fs_re.sub(replace_with, s)
    # Collapse repeated underscores/spaces
    s = re.sub(r"[_\s]{2,}", " ", s)
    return s.strip()


def _category_dir_name(category: str) -> str:
    """
    Turn a human-readable category name into a directory-friendly name.

    Example:
        "Best of 90s" -> "Best_of_90s"
    """
    name = (category or "").strip().replace(" ", "_")
    return _sanitize_filename(name)


def _file_basename(song: "Song") -> str:
    """
    Build the MP3 filename (without directory).

    Pattern: "{Title} - {artist1, artist2}.mp3"
    """
    artists = ", ".join(song.artists) if getattr(song, "artists", None) else ""
    base = f"{song.title} - {artists}".strip()
    base = _sanitize_filename(base)
    if not base.lower().endswith(".mp3"):
        base += ".mp3"
    return base


def expected_path(song: "Song") -> Path:
    """
    Build the path where the MP3 is (or will be) stored.

    For this refactored project we use:
        SONGS_DIR / <CATEGORY_DIR> / "<Title> - <Artists>.mp3"
    """
    root = SONGS_DIR
    cdir = _category_dir_name(song.category)
    base = _file_basename(song)
    return root / cdir / base


def resolve_existing_file(song: "Song", migrate: bool = False) -> Path:
    """
    Returns the most likely on-disk file (existing or future target).

    Currently this is a thin wrapper over expected_path().

    In future, if you introduce legacy layouts or category-rename
    migration, you can extend this to:

      - Check multiple possible locations.
      - If migrate=True and a legacy path exists, move it.

    That behaviour is fully encapsulated here; callers don't need
    to know about the layout history.
    """
    # TODO: move songs between categories in csv files (migrate) is not implemented
    # TODO: also implement songs deletion from csv files
    return expected_path(song)
