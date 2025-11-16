from typing import Dict

from my_player.helpers.constants import DURATION_DB
from my_player.helpers.json_utils import load_json, save_json


def load_dur_db() -> Dict[str, int]:
    return {k: int(v) for k, v in load_json(DURATION_DB, {}).items()}

def save_dur_db(db: Dict[str, int]):
    save_json(DURATION_DB, db)
