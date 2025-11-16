from PyQt6.QtWidgets import QMessageBox, QInputDialog

from my_player.io.library_io import load_library_from_csvs
from my_player.models.song import Song
from my_player.helpers.ui_utils import themed_msg
from my_player.helpers.csv_utils import copy_song_to_category, move_song_between_categories


class CategoryMigrationsMixin:
    def _move_or_copy_category(self, s: Song, do_copy: bool):
        # TODO: invalid use of "move_song_between_categories()" function.
        #  Category migration not implemented. (my_player.helpers.file_utils.resolve_existing_file)
        cats = sorted(self.library.keys())
        if not cats:
            themed_msg(self, QMessageBox.Icon.Information, "No categories", "No categories available.").exec()
            return
        cur = s.category
        try:
            i = max(0, cats.index(cur))
        except ValueError:
            i = 0
        name, ok = QInputDialog.getItem(self, "Select Category", "Target category:", cats, i, False)
        if not ok or not name:
            return
        if name == s.category and not do_copy:
            self.status.showMessage("Already in that category.", 2000)
            return
        try:
            if do_copy:
                copy_song_to_category(name, s)
                self.status.showMessage(f"Copied to “{name}”.", 3000)
            else:
                move_song_between_categories(s, name)
                self.status.showMessage(f"Moved to “{name}”.", 3000)
            # refresh memory + view
            self.library = load_library_from_csvs()
            self._refresh_categories()
            self._apply_search_now()
        except Exception as e:
            themed_msg(self, QMessageBox.Icon.Critical, "Operation failed", f"{e}").exec()
