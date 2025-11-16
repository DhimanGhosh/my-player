import csv
import re
from typing import List, Tuple, Any
from pathlib import Path

from my_player.models.song import Song
from my_player.io.library_io import looks_like_header, column_indices, category_csv_path


def _coerce_row_like(x: Any) -> Tuple[str, str, str]:
    """
    Accept:
      - Song(category, title, album, artists)
      - (title, album, artists) tuple/list
      - dict with keys
    Returns (title, album, artists_str)
    """
    if isinstance(x, Song):
        return x.title, x.album, ", ".join(x.artists)
    if isinstance(x, (tuple, list)) and len(x) >= 3:
        t, a, ar = x[0], x[1], x[2]
        return str(t).strip(), str(a).strip(), str(ar).strip()
    if isinstance(x, dict):
        t = x.get("title", "")
        a = x.get("album", "")
        ar = x.get("artists", x.get("artist", ""))
        if isinstance(ar, (list, tuple)):
            ar = ", ".join(str(z) for z in ar)
        return str(t).strip(), str(a).strip(), str(ar).strip()
    # Fallback: best effort
    return str(x).strip(), "", ""


def _read_category_rows(category: str) -> Tuple[List[str], List[List[str]], Tuple[int, int, int]]:
    """
    Return (header_row, rows, (title_ix, album_ix, artists_ix)).
    header_row is the original header if present (else empty list).
    rows are the body rows (no header).
    """
    p = category_csv_path(category)
    if not p.exists():
        return ["Title", "Album", "Artists"], [], (0, 1, 2)

    with p.open("r", encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        raw = list(reader)

    if not raw:
        return ["Title", "Album", "Artists"], [], (0, 1, 2)

    first = raw[0]
    norm_header = [h.strip().lower().replace(" ", "") for h in first]
    if looks_like_header(norm_header):
        header = first
        body = raw[1:]
        title_ix, album_ix, artists_ix = column_indices(norm_header, default_len=len(first))
    else:
        header = ["Title", "Album", "Artists"]
        body = raw
        title_ix, album_ix, artists_ix = column_indices([], default_len=len(first))

    return header, body, (title_ix, album_ix, artists_ix)


def _normalize_artists_str(s: str) -> str:
    # Normalize delimiters and extra spaces for comparison
    parts = [p.strip() for p in re.split(r"[;/,]", s) if p.strip()]
    return ", ".join(parts)


def _rows_equal(lhs: Tuple[str, str, str], rhs: Tuple[str, str, str]) -> bool:
    lt, la, lar = lhs
    rt, ra, rar = rhs
    if lt.strip() != rt.strip():
        return False
    if la.strip() != ra.strip():
        return False
    return _normalize_artists_str(lar) == _normalize_artists_str(rar)


def _find_row_index(rows: List[List[str]],
                    indices: Tuple[int, int, int],
                    needle: Tuple[str, str, str]) -> int:
    """Find the first row that equals the needle (title, album, artists), else -1."""
    t_ix, a_ix, ar_ix = indices
    for i, r in enumerate(rows):
        t = (r[t_ix] if t_ix < len(r) else "").strip()
        a = (r[a_ix] if a_ix < len(r) else "").strip()
        ar = (r[ar_ix] if ar_ix < len(r) else "").strip()
        if _rows_equal((t, a, ar), needle):
            return i
    return -1


def _write_category_rows(category: str, header: List[str], rows: List[List[str]]) -> Path:
    p = category_csv_path(category)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if header:
            w.writerow(header)
        for r in rows:
            w.writerow(r)
    return p


def copy_song_to_category(target_category: str, song_like: Any) -> bool:
    """
    Copy the given song row (by (title, album, artists)) to target category CSV.
    Returns True if appended, False if a duplicate already exists.
    """
    t, a, ar = _coerce_row_like(song_like)
    header_t, rows_t, idx_t = _read_category_rows(target_category)

    # Check duplicate in target
    if _find_row_index(rows_t, idx_t, (t, a, ar)) != -1:
        return False

    rows_t.append([t, a, ar])
    _write_category_rows(target_category, header_t, rows_t)
    return True


def move_song_between_categories(source_category: str, target_category: str, song_like: Any) -> bool:
    """
    Move the given song row from source CSV to target CSV (cut from source, append to target).
    Returns True if moved; False if source did not contain the row or target already had it.
    """
    t, a, ar = _coerce_row_like(song_like)

    # Read source
    header_s, rows_s, idx_s = _read_category_rows(source_category)
    i = _find_row_index(rows_s, idx_s, (t, a, ar))
    if i == -1:
        return False  # not found in source

    # Read target
    header_t, rows_t, idx_t = _read_category_rows(target_category)

    # Duplicate check on target
    if _find_row_index(rows_t, idx_t, (t, a, ar)) != -1:
        return False  # already in target

    # Move
    row = rows_s.pop(i)
    rows_t.append(row)

    _write_category_rows(source_category, header_s, rows_s)
    _write_category_rows(target_category, header_t, rows_t)
    return True
