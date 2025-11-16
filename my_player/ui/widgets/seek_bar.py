from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSlider


class SeekSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            ratio = event.position().x() / max(1, self.width())
            val = int(self.minimum() + ratio * (self.maximum() - self.minimum()))
            self.setValue(val)
            self.sliderPressed.emit()
            self.sliderReleased.emit()
            event.accept()
        super().mousePressEvent(event)
