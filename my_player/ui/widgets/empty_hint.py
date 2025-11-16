from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QLabel


class EmptyHint(QWidget):
    """Centered 'No result found' hint; call setVisible(True/False)."""
    def __init__(self, parent, text="No result found"):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._label = QLabel(text, self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("font-size:15px; color:#9AA3AD;")
        self.hide()

    def set_text(self, t):
        self._label.setText(t)

    def resizeEvent(self, e):
        self._label.setGeometry(self.rect())
        super().resizeEvent(e)
