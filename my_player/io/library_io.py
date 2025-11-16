import csv
from pathlib import Path
from typing import Dict, List, Iterable, Tuple

from my_player.models.song import Song
from my_player.helpers.constants import LIBRARY_DIR, SONGS_DIR
from my_player.helpers.file_utils import expected_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def looks_like_header(row: List[str]) -> bool:
    """
    Heuristic to decide whether the first row is a header.

    We expect something that looks like columns for title / album / artists.
    """
    lowered = [c.strip().lower() for c in row]
    if not lowered:
        return False

    joined = " ".join(lowered)
    has_title = any("title" in c or "song" in c for c in lowered)
    has_album = any(word in joined for word in ("album", "film", "movie"))
    has_artist = any(word in joined for word in ("artist", "singer", "singers"))

    # Basic sanity: at least 2–3 columns and reasonable header words
    return len(lowered) >= 2 and has_title and (has_album or has_artist)


def column_indices(header_norm: List[str], default_len: int = 0) -> Tuple[int, int, int]:
    """
    Return indices: (title_ix, album_ix, artists_ix).
    If there's no header, default to 0/1/2 defensively.
    """
    if not header_norm:
        return 0, 1, 2

    def _fallback_ix(default_pos: int) -> int:
        if default_len <= 0:
            return default_pos
        return default_pos if default_len > default_pos else (default_len - 1)

    title_ix = next((i for i, h in enumerate(header_norm) if h in ("title", "song")), _fallback_ix(0))
    album_ix = next((i for i, h in enumerate(header_norm) if h in ("album", "film", "film/album", "filmalbum")),
                    _fallback_ix(1))
    artists_ix = next((i for i, h in enumerate(header_norm) if h in ("artists", "artist", "singer", "singers")),
                      _fallback_ix(2))

    return title_ix, album_ix, artists_ix


def _rename_category_csv(old_display_name: str, new_display_name: str) -> Path:
    """
    Rename the CSV file backing a category (display names like 'Kishore Kumar').
    We search 'songs/' for a file whose stem matches the display name
    (case-insensitive), accepting both spaces and underscores.

    Returns the new path if success, else raises Exception.
    """
    if not SONGS_DIR.exists():
        raise FileNotFoundError(f"songs/ folder not found at {SONGS_DIR}")

    def norm_display(s: str) -> str:
        return (s or "").strip().lower().replace("_", " ").replace("-", " ")

    old_norm = norm_display(old_display_name)
    new_norm = norm_display(new_display_name)
    if not new_norm:
        raise ValueError("New category name is empty.")

    # Find the existing CSV matching the old display name
    old_csv = None
    for p in SONGS_DIR.glob("*.csv"):
        stem_norm = norm_display(p.stem)
        if stem_norm == old_norm:
            old_csv = p
            break

    if old_csv is None:
        raise FileNotFoundError(f"Could not find CSV for category “{old_display_name}” in {SONGS_DIR}")

    # Prepare new filename; keep simple/visible mapping: spaces → underscores
    new_filename = new_display_name.replace(" ", "_") + ".csv"
    new_csv = (SONGS_DIR / new_filename).resolve()

    # Prevent accidental overwrite
    if new_csv.exists():
        # If it's literally the same file name (case-only change on case-insensitive FS),
        # allow it; else raise.
        if new_csv.samefile(old_csv):
            return new_csv
        raise FileExistsError(f"A CSV already exists for “{new_display_name}”: {new_csv.name}")

    # Do the rename
    old_csv.rename(new_csv)
    return new_csv


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_library_from_csvs(library_dir: Path | None = None) -> Dict[str, List[Song]]:
    """
    Load all categories from CSVs into a mapping: {category_name: [Song, ...]}.

    - `library_dir` defaults to LIBRARY_DIR.
    - Each `*.csv` file in that directory is treated as a category file.
      The *file name* (without extension, underscores converted to spaces)
      becomes the category name shown in the UI.
    """
    if library_dir is None:
        library_dir = LIBRARY_DIR

    library: Dict[str, List[Song]] = {}

    if not library_dir.exists():
        return library

    for csv_path in sorted(library_dir.glob("*.csv")):
        # Category name is derived from the file name
        category_name = csv_path.stem.replace("_", " ").strip()
        songs: List[Song] = []

        try:
            with csv_path.open("r", encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                rows = list(reader)
        except OSError:
            # Skip any unreadable file
            continue

        if not rows:
            continue

        first_row = rows[0]
        has_header = looks_like_header(first_row)

        if has_header:
            title_idx, album_idx, artist_idx = column_indices(first_row)
            data_rows = rows[1:]
        else:
            title_idx, album_idx, artist_idx = column_indices(first_row)
            data_rows = rows

        for row in data_rows:
            if not row:
                continue

            # Defensive: rows can be shorter than expected
            def safe_get(idx: int) -> str:
                return row[idx].strip() if idx < len(row) else ""

            title = safe_get(title_idx)
            album = safe_get(album_idx)
            artists_raw = safe_get(artist_idx)

            if not title:
                # no title -> skip; it's likely junk
                continue

            artists = [a.strip() for a in artists_raw.split(",") if a.strip()]

            songs.append(
                Song(
                    category=category_name,
                    title=title,
                    album=album,
                    artists=artists,
                )
            )

        if songs:
            library[category_name] = songs

    return library


def category_csv_path(
    category_name: str,
    library_dir: Path | None = None,
) -> Path:
    """
    Return the CSV path for a given human-readable category name.

    - Spaces are converted to underscores.
    - Unsafe characters are stripped.
    """
    import re

    if library_dir is None:
        library_dir = LIBRARY_DIR

    # Normalise the category file name
    cleaned = re.sub(r"[^0-9A-Za-z _-]+", "", category_name).strip()
    if not cleaned:
        cleaned = "Unnamed"

    filename = cleaned.replace(" ", "_") + ".csv"
    return library_dir / filename


def append_rows_to_category_csv(
    category_name: str,
    rows: Iterable[Tuple[str, str, str]],
    library_dir: Path | None = None,
) -> Path:
    """
    Append one or more rows to the category CSV.

    Parameters
    ----------
    category_name:
        Human-readable category name (what you show in the UI).
    rows:
        Iterable of (title, album, artists_string).

        NOTE: This function stays intentionally dumb:
        it assumes the caller already did any trimming / validation.

    Returns
    -------
    Path
        The CSV file path that was written to.
        :param category_name:
        :param rows:
        :param library_dir:
    """
    if library_dir is None:
        library_dir = LIBRARY_DIR

    csv_path = category_csv_path(category_name, library_dir)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    # If file does not exist, write a simple header first
    file_exists = csv_path.exists()

    with csv_path.open("a", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)

        if not file_exists:
            writer.writerow(["title", "album", "artists"])

        for title, album, artists in rows:
            writer.writerow([title, album, artists])

    return csv_path


def rename_category_everywhere(
    old_cat: str,
    new_cat: str,
    library: Dict[str, List[Song]]
) -> List[Tuple[Tuple[str, str, str, str], Tuple[str, str, str, str]]]:
    """
    Rename a category across CSV and filesystem, and move any downloaded files to the new
    expected location. Returns a list of (old_key, new_key) for all songs in the renamed category.

    Uses expected_path() before/after to avoid guessing directory names.
    Also removes the old category directory if it becomes empty.
    """
    # 1) Rename the backing CSV
    _rename_category_csv(old_cat, new_cat)

    # 2) Move downloaded files for songs in this category
    moved_key_pairs: List[Tuple[Tuple[str, str, str, str], Tuple[str, str, str, str]]] = []
    songs_in_old = library.get(old_cat, [])

    for s in songs_in_old:
        old_song = s
        new_song = Song(title=s.title, album=s.album, artists=s.artists, category=new_cat)

        old_path = expected_path(old_song)
        new_path = expected_path(new_song)

        try:
            new_path.parent.mkdir(parents=True, exist_ok=True)
            if old_path.exists():
                if new_path.exists() and new_path != old_path:
                    try:
                        new_path.unlink()
                    except Exception:
                        pass
                old_path.replace(new_path)
        except Exception:
            # Continue even if a particular file couldn't be moved
            pass

        moved_key_pairs.append((old_song.key(), new_song.key()))

    # 3) Best-effort: remove the now-empty old category directory
    try:
        if songs_in_old:
            sample_old_dir = expected_path(
                Song(
                    title=songs_in_old[0].title,
                    album=songs_in_old[0].album,
                    artists=songs_in_old[0].artists,
                    category=old_cat,
                )
            ).parent
            if sample_old_dir.exists() and not any(sample_old_dir.iterdir()):
                sample_old_dir.rmdir()
    except Exception:
        pass

    return moved_key_pairs
