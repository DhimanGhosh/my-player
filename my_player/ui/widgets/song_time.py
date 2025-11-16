from PyQt6.QtWidgets import QLabel


class SongTimeLabelMMSS(QLabel):
    def __init__(self):
        super().__init__("00:00 / 00:00")
        self.setMinimumWidth(110)

    def set_times(self, cur: str, total: str):
        self.setText(f"{cur} / {total}")
