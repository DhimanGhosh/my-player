import csv
from collections import defaultdict
from typing import Dict, List, Any

from my_player.helpers.constants import (
    SONGLINK_RAW_DATASET,
    SONGLINK_TRAIN_DATASET,
    MIN_SEC,
    MAX_SEC,
    BAD_SEARCH_KEYWORDS,
    OFFICIAL_YOUTUBE_CHANNELS
)


def _load_raw_rows() -> List[Dict[str, Any]]:
    if not SONGLINK_RAW_DATASET.exists():
        raise FileNotFoundError(f"Raw dataset not found: {SONGLINK_RAW_DATASET}")

    rows: List[Dict[str, Any]] = []
    with SONGLINK_RAW_DATASET.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Clean BOM from query if present
            q = (row.get("query") or "").strip().lstrip("\ufeff")
            row["query"] = q

            # Normalize text fields
            row["title"] = (row.get("title") or "").strip()
            row["channel"] = (row.get("channel") or "").strip()
            row["description"] = (row.get("description") or "").strip()

            # Duration as int
            try:
                row["duration"] = int(float(row.get("duration") or 0))
            except ValueError:
                row["duration"] = 0

            # label_hint, label as ints if present
            try:
                row["label_hint"] = int(row.get("label_hint", 0))
            except ValueError:
                row["label_hint"] = 0

            rows.append(row)
    return rows


def _is_bad_candidate(row: Dict[str, Any]) -> bool:
    """
    Use BAD_SEARCH_KEYWORDS to filter obviously wrong items:
    lofi, 8d, remix, status, jukebox, full album, etc.
    """
    text = f"{row['title']} || {row['description']}".lower()
    for bad_kw in BAD_SEARCH_KEYWORDS:
        if bad_kw.lower() in text:
            return True
    return False


def _is_duration_ok(row: Dict[str, Any]) -> bool:
    """
    Full songs should fall within MIN_SEC and MAX_SEC.
    """
    d = row["duration"]
    if d <= 0:
        return False
    return MIN_SEC <= d <= MAX_SEC


def _is_official_channel(row: Dict[str, Any]) -> bool:
    """
    Prefer official-ish channels.
    """
    ch = row["channel"].lower()
    for cname in OFFICIAL_YOUTUBE_CHANNELS:
        if cname.lower() in ch:
            return True
    return False


def _choose_best_for_query(rows: List[Dict[str, Any]]) -> int | None:
    """
    Given all candidates for a single query, pick one index to mark as label=1.

    Strategy:
      1) Filter out BAD_SEARCH_KEYWORDS.
      2) Filter by duration range.
      3) Among remaining, prefer official channels.
      4) Among remaining, prefer label_hint=1.
      5) If nothing left, fallback to label_hint=1 among all.
      6) If still nothing, pick first row.
    Returns index in 'rows' or None if nothing reasonable.
    """
    # Step 1 & 2: filter candidates
    good_indices: List[int] = []
    for i, r in enumerate(rows):
        if _is_bad_candidate(r):
            continue
        if not _is_duration_ok(r):
            continue
        good_indices.append(i)

    if not good_indices:
        # fallback: at least try label_hint=1 among all
        hinted = [i for i, r in enumerate(rows) if r.get("label_hint", 0) == 1]
        if hinted:
            return hinted[0]
        # last resort: first row
        return 0 if rows else None

    # Prefer official channels among good_indices
    official_indices = [i for i in good_indices if _is_official_channel(rows[i])]
    candidate_pool = official_indices if official_indices else good_indices

    # Prefer label_hint=1 in candidate_pool
    hinted = [i for i in candidate_pool if rows[i].get("label_hint", 0) == 1]
    if hinted:
        return hinted[0]

    # Else just pick the first from candidate_pool
    return candidate_pool[0]


def build_train_dataset() -> None:
    """
    Read SONGLINK_RAW_DATASET, auto-label, write SONGLINK_TRAIN_DATASET
    with schema: query,title,channel,description,duration,label,url
    """
    raw_rows = _load_raw_rows()
    if not raw_rows:
        print("[ERROR] No rows in raw dataset.")
        return

    # Group by query
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in raw_rows:
        groups[r["query"]].append(r)

    print(f"[INFO] Found {len(groups)} unique queries in raw dataset.")

    SONGLINK_TRAIN_DATASET.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = ["query", "title", "channel", "description", "duration", "label", "url"]

    with SONGLINK_TRAIN_DATASET.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for q, rows in groups.items():
            best_idx = _choose_best_for_query(rows)

            for i, r in enumerate(rows):
                label = 1 if i == best_idx else 0
                writer.writerow({
                    "query": r["query"],
                    "title": r["title"],
                    "channel": r["channel"],
                    "description": r["description"],
                    "duration": r["duration"],
                    "label": label,
                    "url": r.get("url", ""),
                })

    print(f"[INFO] Wrote labeled training dataset to: {SONGLINK_TRAIN_DATASET}")


if __name__ == "__main__":
    build_train_dataset()
