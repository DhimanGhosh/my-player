from typing import Dict, List

from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from my_player.models.song import Song
from my_player.helpers.file_utils import expected_path


class _ScanMissingTaskSignals(QObject):
    done = pyqtSignal(list)  # List[Song]


class ScanMissingTask(QRunnable):
    def __init__(self, library: Dict[str, List[Song]]):
        super().__init__()
        self.library = library
        self.signals = _ScanMissingTaskSignals()

    def run(self):
        miss: List[Song] = []
        for rows in self.library.values():
            for s in rows:
                try:
                    if not expected_path(s).exists():
                        miss.append(s)
                except Exception:
                    # Ignore bad rows
                    pass
        self.signals.done.emit(miss)
