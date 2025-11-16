from typing import List

from PyQt6.QtCore import pyqtSlot, QThreadPool

from my_player.signals.missing_task import ScanMissingTask
from my_player.models.song import Song


class BackgroundScanMixin:
    def _kick_background_missing_scan(self):
        """Runs the missing-scan on a worker thread, then enqueues on DownloadManager."""
        self.status.showMessage("Scanning library for missing files…", 2000)
        task = ScanMissingTask(self.library)
        task.signals.done.connect(self._on_missing_scanned)
        QThreadPool.globalInstance().start(task)

    @pyqtSlot(list)
    def _on_missing_scanned(self, missing: List[Song]):
        if not missing:
            self.status.showMessage("All songs present.", 1500)
            return
        self.dlm.resume_background()
        self.dlm.enqueue_background_many(missing)
        self.status.showMessage(f"Background: queued {len(missing)} missing song(s).", 4000)
