from typing import Dict, List

from PyQt6.QtCore import QObject, pyqtSignal, QRunnable

from my_player.models.song import Song
from my_player.helpers.utils import norm


class _SearchSignals(QObject):
    done = pyqtSignal(int, object)  # seq, List[Song]


class SearchTask(QRunnable):
    def __init__(self, seq: int, mode: str, query: str, library: Dict[str, List[Song]], base_list: List[Song]):
        super().__init__()
        self.seq = seq
        self.mode = mode  # "Category" or "Global"
        self.query = query
        self.library = library
        self.base_list = base_list
        self.signals = _SearchSignals()

    def run(self):
        q = (self.query or "").strip()
        if self.mode == "Category":
            songs = self._filter_any(self.base_list, q)
        else:
            if not q:
                songs = [s for rows in self.library.values() for s in rows]
            else:
                everything = [s for rows in self.library.values() for s in rows]
                songs = self._filter_any(everything, q)
        self.signals.done.emit(self.seq, songs)

    @staticmethod
    def _filter_any(rows: List[Song], query: str) -> List[Song]:
        if not query:
            return list(rows)
        toks = norm(query).split()
        out: List[Song] = []
        for s in rows:
            hay = " | ".join([s.category, s.title, s.album, ", ".join(s.artists)]).lower()
            hay_n = norm(hay)
            if all(tok in hay_n for tok in toks):
                out.append(s)
        return out
