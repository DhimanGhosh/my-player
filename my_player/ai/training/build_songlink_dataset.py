import csv
import json
import subprocess
import sys
from typing import List, Dict

from my_player.helpers.constants import (
    AI_DATA_DIR,
    SONGLINK_QUERIES_TXT,
    SONGLINK_RAW_DATASET,
    YTDP_LIMIT_PER_QUERY
)


def _load_queries() -> List[str]:
    """
    Load queries from SONGLINK_QUERIES_TXT with auto-detected encoding.
    Handles UTF-8, UTF-8 BOM, UTF-16 LE, UTF-16 BE safely and strips BOM.
    """
    queries: List[str] = []

    if not SONGLINK_QUERIES_TXT.exists():
        print(f"[ERROR] Query file not found: {SONGLINK_QUERIES_TXT}")
        return []

    raw = SONGLINK_QUERIES_TXT.read_bytes()

    # Detect BOM
    if raw.startswith(b'\xff\xfe'):
        text = raw.decode("utf-16-le", errors="ignore")
    elif raw.startswith(b'\xfe\xff'):
        text = raw.decode("utf-16-be", errors="ignore")
    elif raw.startswith(b'\xef\xbb\xbf'):
        text = raw.decode("utf-8-sig", errors="ignore")
    else:
        text = raw.decode("utf-8", errors="ignore")

    for line in text.splitlines():
        q = line.strip().lstrip("\ufeff")
        if q:
            queries.append(q)

    return queries


def _fetch_candidates(query: str, limit: int = 10) -> List[Dict]:
    """
    Fetch YouTube search candidates using yt-dlp JSON output.
    """
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "-j",
        f"ytsearch{limit}:{query}",
        "--no-playlist",
    ]

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except Exception as e:
        print(f"[ERROR] yt-dlp failed for '{query}': {e}")
        return []

    if proc.returncode != 0:
        print(f"[WARN] yt-dlp returned {proc.returncode} for '{query}'")
        return []

    candidates = []
    for line in proc.stdout.splitlines():
        try:
            info = json.loads(line)
        except Exception:
            continue

        url = info.get("webpage_url") or info.get("url")
        title = info.get("title")
        if not url or not title:
            continue

        candidates.append({
            "query": query,
            "title": title,
            "channel": info.get("channel") or "",
            "description": info.get("description") or "",
            "duration": info.get("duration") or 0,
            "label": 0,         # manually correct later
            "label_hint": 1 if len(candidates) == 0 else 0,
            "url": url,
        })

    return candidates


def build_dataset() -> None:
    """
    Build raw dataset from queries and write into SONGLINK_RAW_DATASET.
    """
    AI_DATA_DIR.mkdir(parents=True, exist_ok=True)

    queries = _load_queries()
    if not queries:
        print("[ERROR] No queries loaded.")
        return

    fieldnames = [
        "query", "title", "channel", "description",
        "duration", "label", "label_hint", "url"
    ]

    with SONGLINK_RAW_DATASET.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for idx, q in enumerate(queries, start=1):
            print(f"[INFO] Fetching candidates {idx}/{len(queries)} → {q}")
            results = _fetch_candidates(q, limit=YTDP_LIMIT_PER_QUERY)
            if results:
                writer.writerows(results)

    print(f"[INFO] Dataset written to: {SONGLINK_RAW_DATASET}")


if __name__ == "__main__":
    build_dataset()
