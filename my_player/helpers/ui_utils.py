from PyQt6.QtWidgets import QMessageBox

from my_player.ui.theme import MaterialTheme


def themed_msg(parent, icon: QMessageBox.Icon, title: str, text: str,
               buttons: QMessageBox.StandardButton = QMessageBox.StandardButton.Ok) -> QMessageBox:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    box.setIcon(icon)
    box.setStandardButtons(buttons)
    box.setStyleSheet(MaterialTheme.stylesheet())
    return box
