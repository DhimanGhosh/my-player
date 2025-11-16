from typing import List, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QLineEdit,
    QCheckBox, QDialogButtonBox, QMessageBox
)

from my_player.ui.theme import MaterialTheme
from my_player.models.song import Song
from my_player.helpers.ui_utils import themed_msg


class AddCategoryDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add / Append Category")
        self.setModal(True)
        self.setStyleSheet(MaterialTheme.stylesheet())
        self.rows: List[Song] = []
        self.category: Optional[str] = None

        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.category_edit = QLineEdit(); form.addRow("Category name:", self.category_edit)
        self.song_edit = QLineEdit(); self.album_edit = QLineEdit(); self.artists_edit = QLineEdit()
        form.addRow("Song:", self.song_edit)
        form.addRow("Film/Album:", self.album_edit)
        form.addRow("Artists (comma-separated):", self.artists_edit)

        self.add_more = QCheckBox("I want to add multiple rows"); self.add_more.setChecked(True)
        lay.addLayout(form); lay.addWidget(self.add_more)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept_row); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def accept_row(self):
        cat = self.category_edit.text().strip()
        title = self.song_edit.text().strip()
        album = self.album_edit.text().strip()
        artists = [a.strip() for a in self.artists_edit.text().split(",") if a.strip()]
        if not cat or not title:
            themed_msg(self, QMessageBox.Icon.Warning, "Missing", "Please enter at least Category and Song.").exec()
            return
        self.category = cat
        self.rows.append(Song(title=title, album=album, artists=artists, category=cat))
        if self.add_more.isChecked():
            self.song_edit.clear()
            self.album_edit.clear()
            self.artists_edit.clear()
            self.song_edit.setFocus()
        else:
            self.accept()
