from PyQt6.QtCore import Qt, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtWidgets import QWidget, QLabel
from PyQt6.QtGui import QPainter, QColor


class BusyOverlay(QWidget):
    """Mouse-transparent dark veil with centered text."""
    def __init__(self, parent, text="Working…"):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)
        self._opacity = 0.0
        self._label = QLabel(text, self)
        self._label.setStyleSheet("font-size:16px; font-weight:600;")
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hide()

    def set_text(self, t):
        self._label.setText(t)

    def resizeEvent(self, e):
        self._label.setGeometry(self.rect())
        super().resizeEvent(e)

    def paintEvent(self, _):
        if self._opacity <= 0: return
        p = QPainter(self)
        c = QColor(0, 0, 0, int(180 * self._opacity))
        p.fillRect(self.rect(), c)

    def _set_opacity(self, v):
        self._opacity = max(0.0, min(1.0, float(v)))
        self.update()

    def _get_opacity(self): return self._opacity
    opacity = pyqtProperty(float, fget=_get_opacity, fset=_set_opacity)

    def fade_in(self):
        self.show()
        anim = QPropertyAnimation(self, b"opacity")
        anim.setDuration(160); anim.setStartValue(self._opacity); anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def fade_out(self):
        anim = QPropertyAnimation(self, b"opacity")
        anim.setDuration(160); anim.setStartValue(self._opacity); anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(self.hide)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
