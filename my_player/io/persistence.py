import csv
from pathlib import Path
from typing import List

from my_player.models.song import Song
from my_player.helpers.file_utils import safe_filename
from my_player.helpers.constants import SONGS_DIR


def _read_rows(csv_path: Path) -> List[list[str]]:
    rows: List[list[str]] = []
    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
            for r in csv.reader(fh):
                if len(r) >= 3:
                    rows.append([r[0], r[1], r[2]])
    return rows


def _write_rows(csv_path: Path, rows: List[list[str]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows(rows)


def _append_row(csv_path: Path, row: list[str]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("a", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerow(row)


def _csv_for_category(name: str) -> Path:
    return SONGS_DIR / f"{safe_filename(name.upper().replace(' ', '_'))}.csv"


def update_song_row(old: Song, new: Song) -> None:
    """Persist inline edits back to CSV; move rows if category changed."""
    old_csv = _csv_for_category(old.category)
    new_csv = _csv_for_category(new.category)

    old_rows = _read_rows(old_csv)
    try:
        old_rows.remove([old.title, old.album, ", ".join(old.artists)])
    except ValueError:
        pass

    if old_csv == new_csv:
        # Update in place
        old_rows.append([new.title, new.album, ", ".join(new.artists)])
        _write_rows(old_csv, old_rows)
    else:
        # Move row across CSVs
        _write_rows(old_csv, old_rows)
        _append_row(new_csv, [new.title, new.album, ", ".join(new.artists)])
