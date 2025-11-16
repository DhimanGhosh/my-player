import json
from pathlib import Path
from typing import Any


def load_json(path: Path, default: Any) -> Any:
    """
    Safe JSON loader: returns `default` if file doesn't exist or is invalid.
    """
    try:
        if not path.exists():
            return default
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    """
    Safe JSON saver.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        # Best-effort; errors are not fatal
        pass
