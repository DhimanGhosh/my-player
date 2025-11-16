from PyQt6.QtWidgets import QTableWidgetItem, QMessageBox

from my_player.models.song import Song
from my_player.helpers.ui_utils import themed_msg
from my_player.io.library_io import load_library_from_csvs
from my_player.io.persistence import update_song_row


class InlineEditMixin:
    """
    Handles inline editing of table cells and persisting those edits to CSV.

    Expects the main window to provide:

      Attributes:
        self.table           # QTableWidget
        self.current_list    # List[Song]
        self.library         # Dict[str, List[Song]]
        self.status          # QStatusBar

      Methods:
        self._refresh_categories()
    """

    # Must match main window’s column indices
    COL_FAV = 0
    COL_CATEGORY = 1
    COL_TITLE = 2
    COL_ALBUM = 3
    COL_ARTISTS = 4
    COL_DURATION = 5

    # ---------- Inline edit + persist ----------

    def _enable_table_editing(self) -> None:
        """
        Enable inline editing on specific columns and connect itemChanged
        to _on_item_changed. Call this once during UI setup.
        """
        self.table.setEditTriggers(
            self.table.EditTrigger.DoubleClicked
            | self.table.EditTrigger.SelectedClicked
        )
        try:
            self.table.itemChanged.disconnect(self._on_item_changed)
        except Exception:
            pass
        self.table.itemChanged.connect(self._on_item_changed)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """
        Persist edits to category / title / album / artists back to CSV via
        update_song_row(old, new). Mirrors original logic.
        """
        r, c = item.row(), item.column()
        if not (0 <= r < len(self.current_list)):
            return

        if c not in (
            self.COL_CATEGORY,
            self.COL_TITLE,
            self.COL_ALBUM,
            self.COL_ARTISTS,
        ):
            return

        old = self.current_list[r]

        # Read edited values from the row, falling back to old if missing.
        cat_item = self.table.item(r, self.COL_CATEGORY)
        tit_item = self.table.item(r, self.COL_TITLE)
        alb_item = self.table.item(r, self.COL_ALBUM)
        art_item = self.table.item(r, self.COL_ARTISTS)

        new_cat = cat_item.text() if cat_item else old.category
        new_t = tit_item.text() if tit_item else old.title
        new_al = alb_item.text() if alb_item else old.album
        new_ar_s = art_item.text() if art_item else ", ".join(old.artists)

        new = Song(
            category=new_cat,
            title=new_t,
            album=new_al,
            artists=[x.strip() for x in new_ar_s.split(",") if x.strip()],
        )

        try:
            # Persist to CSV
            update_song_row(old, new)

            # Reload library in memory and update current row object
            self.library = load_library_from_csvs()
            self.current_list[r] = new
            self._refresh_categories()
            self.status.showMessage("Saved edit to CSV.", 2000)

        except Exception as e:
            # On failure, restore original values in the table
            themed_msg(
                self,
                QMessageBox.Icon.Critical,
                "Edit failed",
                f"{e}",
            ).exec()

            self.table.blockSignals(True)
            self.table.setItem(
                r, self.COL_CATEGORY, QTableWidgetItem(old.category)
            )
            self.table.setItem(
                r, self.COL_TITLE, QTableWidgetItem(old.title)
            )
            self.table.setItem(
                r, self.COL_ALBUM, QTableWidgetItem(old.album)
            )
            self.table.setItem(
                r,
                self.COL_ARTISTS,
                QTableWidgetItem(", ".join(old.artists)),
            )
            self.table.blockSignals(False)
