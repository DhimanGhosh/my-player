from typing import Dict

from my_player.helpers.constants import HISTORY_DB, CUSTOM_SOURCE_DB
from my_player.helpers.json_utils import load_json, save_json


def load_history() -> Dict[str, dict]:
    raw = load_json(HISTORY_DB, {})
    if not isinstance(raw, dict):
        return {}
    return raw


def save_history(history: Dict[str, dict]) -> None:
    save_json(HISTORY_DB, history)


def load_custom() -> Dict[str, str]:
    raw = load_json(CUSTOM_SOURCE_DB, {})
    if not isinstance(raw, dict):
        return {}
    return raw

def save_custom(custom: Dict[str, str]) -> None:
    save_json(CUSTOM_SOURCE_DB, custom)


def key_str(key: tuple) -> str:
    """
    Convert a 4-tuple key to a string for history/custom mapping.
    """
    return "||".join(key)
