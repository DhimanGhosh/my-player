import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication

from my_player.ui.main_window import MyPlayerMain
from my_player.helpers.constants import SONGS_DIR


def main():
    SONGS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass

    app = QApplication(sys.argv)
    win = MyPlayerMain()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
