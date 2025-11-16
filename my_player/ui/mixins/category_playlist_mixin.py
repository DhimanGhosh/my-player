from typing import Dict, List, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QMenu,
    QMessageBox,
    QInputDialog
)

from my_player.helpers.ui_utils import themed_msg
from my_player.helpers.db_utils import save_dur_db
from my_player.helpers.file_utils import expected_path
from my_player.helpers.constants import (
    SPECIAL_FAV_CATEGORY,
    SPECIAL_PL_CATEGORY_PREFIX
)
from my_player.io.library_io import (
    load_library_from_csvs,
    append_rows_to_category_csv,
    rename_category_everywhere
)
from my_player.ui.theme import MaterialTheme
from my_player.ui.dialogs.add_category_dialog import AddCategoryDialog
from my_player.models.song import Song


class CategoryPlaylistMixin:
    """
    Mixin for MyPlayerMain:

    - Category / playlist panel refresh
    - Left-pane context menus
    - Rename category / playlist (plus all the remapping)
    - Add category via CSV dialog
    - View label helpers
    - View identity + base list resolution
    """

    # --- Categories / Playlists panels ------------------------------------

    def _refresh_categories(self) -> None:
        """Rebuild the Categories list widget from self.library."""
        self.category_list.clear()
        cats = sorted(self.library.keys())
        self.category_list.addItems(cats)

        if self.current_category and self.current_category in cats:
            self.category_list.setCurrentRow(cats.index(self.current_category))

    def _refresh_playlists_panel(self) -> None:
        """Rebuild the Playlists list widget from self.playlists."""
        self.playlist_list.clear()
        self.playlist_list.addItems(sorted(self.playlists.keys()))

    def _on_cat_selected(self) -> None:
        """Triggered when user selects a category in the left pane."""
        items = self.category_list.selectedItems()
        if not items:
            return

        self.current_category = items[0].text()
        self.playlist_list.clearSelection()
        self._sync_view_label_from_state()
        self._save_state()
        self._apply_search_now()

    def _on_pl_selected(self) -> None:
        """Triggered when user selects a playlist in the left pane."""
        items = self.playlist_list.selectedItems()
        if not items:
            return

        name = items[0].text()
        self.current_category = f"{SPECIAL_PL_CATEGORY_PREFIX}{name}"
        self.category_list.clearSelection()
        self._sync_view_label_from_state()
        self._save_state()

        self._set_busy(True, "Rendering results…")
        base = self._songs_from_keys(self.playlists.get(name, []))
        self._populate_table_async(base)

    # --- View label / title ----------------------------------------------

    def _set_view_label(self, text: str) -> None:
        """Set the main view label + window title."""
        self.view_label.setText(f"<b>{text}</b>")
        self.setWindowTitle(f"{self.APP_NAME} — {text}" if hasattr(self, "APP_NAME") else text)

    def _sync_view_label_from_state(self) -> None:
        """Update label based on current_category (fav/playlist/category/none)."""
        if self.current_category == SPECIAL_FAV_CATEGORY:
            self._set_view_label("Favourites")
            self.remove_pl_sel_btn.setVisible(False)
        elif self.current_category and self.current_category.startswith(SPECIAL_PL_CATEGORY_PREFIX):
            name = self.current_category[len(SPECIAL_PL_CATEGORY_PREFIX):]
            self._set_view_label(f"Playlist: {name}")
            self.remove_pl_sel_btn.setVisible(True)
        elif self.current_category:
            self._set_view_label(f"Category: {self.current_category}")
            self.remove_pl_sel_btn.setVisible(False)
        else:
            self._set_view_label("Category: (none)")
            self.remove_pl_sel_btn.setVisible(False)

    # --- Category / playlist context menus --------------------------------

    def _open_category(self, name: str) -> None:
        """Open a given category in the main view."""
        self.current_category = name
        self.category_list.clearSelection()
        items = self.category_list.findItems(name, Qt.MatchFlag.MatchExactly)
        if items:
            self.category_list.setCurrentItem(items[0])

        self.playlist_list.clearSelection()
        self._sync_view_label_from_state()
        self._save_state()
        self._apply_search_now()

    def _category_context_menu(self, pos) -> None:
        item = self.category_list.itemAt(pos)
        if not item:
            return

        name = item.text()
        menu = QMenu(self)
        menu.setStyleSheet(MaterialTheme.stylesheet())
        menu.addAction(QAction("Open", self, triggered=lambda: self._open_category(name)))
        menu.addAction(
            QAction(
                "Rename…",
                self,
                triggered=lambda: self._rename_category_or_playlist(name),
            )
        )
        menu.exec(self.category_list.mapToGlobal(pos))

    def _playlist_context_menu(self, pos) -> None:
        item = self.playlist_list.itemAt(pos)
        if not item:
            return

        name = item.text()
        menu = QMenu(self)
        menu.setStyleSheet(MaterialTheme.stylesheet())

        menu.addAction(QAction("Open", self, triggered=lambda: self._open_playlist(name)))
        menu.addAction(
            QAction(
                "Rename…",
                self,
                triggered=lambda: self._rename_category_or_playlist(
                    f"{SPECIAL_PL_CATEGORY_PREFIX}{name}"
                ),
            )
        )

        def _delete():
            box = themed_msg(
                self,
                QMessageBox.Icon.Warning,
                "Delete Playlist?",
                (
                    f"Delete playlist “{name}” and all its references?\n"
                    f"(Downloaded files remain on disk.)"
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if box.exec() == QMessageBox.StandardButton.Yes:
                self.playlists.pop(name, None)
                self._save_state()
                self._refresh_playlists_panel()
                if self.current_category == f"{SPECIAL_PL_CATEGORY_PREFIX}{name}":
                    self.current_category = None
                    self._apply_search_now()

        menu.addAction(QAction("Delete…", self, triggered=_delete))
        menu.exec(self.playlist_list.mapToGlobal(pos))

    # --- Rename Category / Playlist --------------------------------------

    def _rename_category_or_playlist(self, name_or_prefixed: str) -> None:
        """
        Rename a category or playlist.

        - For playlists, only in-memory mapping + state are updated.
        - For categories, CSV files + library + favourites + playlists +
          history + duration cache + custom URLs are remapped using
          rename_category_everywhere(..).
        """
        # ---- Playlist path ----
        if isinstance(name_or_prefixed, str) and name_or_prefixed.startswith(
            SPECIAL_PL_CATEGORY_PREFIX
        ):
            old_pl = name_or_prefixed[len(SPECIAL_PL_CATEGORY_PREFIX):]
            if not old_pl or old_pl not in self.playlists:
                themed_msg(
                    self,
                    QMessageBox.Icon.Information,
                    "Not found",
                    f"Playlist “{old_pl}” doesn’t exist.",
                ).exec()
                return

            new_pl, ok = QInputDialog.getText(
                self,
                "Rename Playlist",
                f"New name for playlist “{old_pl}”:",
            )
            if not ok:
                return

            new_pl = (new_pl or "").strip()
            if not new_pl or new_pl == old_pl:
                return

            if new_pl in self.playlists:
                themed_msg(
                    self,
                    QMessageBox.Icon.Warning,
                    "Already exists",
                    f"A playlist named “{new_pl}” already exists.",
                ).exec()
                return

            self.playlists[new_pl] = self.playlists.pop(old_pl)
            self._save_state()
            self._rebuild_playlists_menu()

            if self.current_category == f"{SPECIAL_PL_CATEGORY_PREFIX}{old_pl}":
                self.current_category = f"{SPECIAL_PL_CATEGORY_PREFIX}{new_pl}"
                self._sync_view_label_from_state()
                self._apply_search_now()

            self.status.showMessage(f"Renamed playlist to “{new_pl}”.", 2500)
            return

        # ---- Category path ----
        old_cat = name_or_prefixed
        if not old_cat or old_cat not in self.library:
            themed_msg(
                self,
                QMessageBox.Icon.Information,
                "Not found",
                f"Category “{old_cat}” doesn’t exist.",
            ).exec()
            return

        new_cat, ok = QInputDialog.getText(
            self,
            "Rename Category",
            f"New name for category “{old_cat}”:",
        )
        if not ok:
            return

        new_cat = (new_cat or "").strip()
        if not new_cat or new_cat == old_cat:
            return

        if new_cat in self.library:
            themed_msg(
                self,
                QMessageBox.Icon.Warning,
                "Already exists",
                f"A category named “{new_cat}” already exists.",
            ).exec()
            return

        # IO + mapping
        try:
            moved_pairs: List[Tuple[Tuple[str, str, str, str], Tuple[str, str, str, str]]] = (
                rename_category_everywhere(old_cat, new_cat, self.library)
            )
        except Exception as e:
            themed_msg(
                self,
                QMessageBox.Icon.Critical,
                "Rename failed",
                f"{e}",
            ).exec()
            return

        # Reload library to reflect new CSVs + categories
        self.library = load_library_from_csvs()

        # --- Favourites remap ---
        if getattr(self, "favourites", None):
            conv = dict(moved_pairs)
            self.favourites = {conv.get(k, k) for k in self.favourites}

        # --- Playlists remap ---
        if getattr(self, "playlists", None):
            conv = dict(moved_pairs)
            for pl_name, lst in list(self.playlists.items()):
                self.playlists[pl_name] = [conv.get(k, k) for k in lst]

        # --- Last/current keys & current_category ---
        if getattr(self, "last_song_key", None) and self.last_song_key[0] == old_cat:
            self.last_song_key = (
                new_cat,
                self.last_song_key[1],
                self.last_song_key[2],
                self.last_song_key[3],
            )

        if getattr(self, "current_song_key", None) and self.current_song_key[0] == old_cat:
            self.current_song_key = (
                new_cat,
                self.current_song_key[1],
                self.current_song_key[2],
                self.current_song_key[3],
            )

        if self.current_category == old_cat:
            self.current_category = new_cat
            self._sync_view_label_from_state()

        # --- History remap ---
        if getattr(self, "history", None):
            conv_hist = {"||".join(ok): "||".join(nk) for ok, nk in moved_pairs}
            self.history = {conv_hist.get(k, k): v for k, v in self.history.items()}

        # --- Duration cache remap (song-key + path-key) ---
        if getattr(self, "duration_db", None):
            conv_dur = {"|".join(ok): "|".join(nk) for ok, nk in moved_pairs}
            new_db: Dict[str, int] = {
                conv_dur.get(k, k): v for k, v in self.duration_db.items()
            }

            # Seed path-keys for renamed songs
            for _, nk in moved_pairs:
                s_new = Song(
                    category=nk[0],
                    title=nk[1],
                    album=nk[2],
                    artists=[
                        x.strip()
                        for x in nk[3].split(",")
                        if x.strip()
                    ],
                )
                p_new = expected_path(s_new)
                k_song = "|".join(nk)
                if k_song in new_db and str(p_new) not in new_db:
                    new_db[str(p_new)] = new_db[k_song]

            self.duration_db = new_db
            save_dur_db(self.duration_db)

        # --- Custom URLs remap (exact keys only, leave *|| wildcards alone) ---
        if getattr(self, "custom_urls", None):
            conv_urls = {"||".join(ok): "||".join(nk) for ok, nk in moved_pairs}
            self.custom_urls = {
                (conv_urls.get(k, k) if not k.startswith("*||") else k): v
                for k, v in self.custom_urls.items()
            }

        # --- Refresh UI ---
        self._refresh_categories()
        self._rebuild_playlists_menu()
        self._save_state()
        self._apply_search_now()
        self.status.showMessage(f"Renamed category to “{new_cat}”.", 2500)

    # --- Add Category via CSV dialog -------------------------------------
    def _reload_csvs(self):
        self.library = load_library_from_csvs()
        self._refresh_categories()
        self._sync_view_label_from_state()
        self._apply_search_now()
        self._rebuild_playlists_menu()
        self._refresh_playlists_panel()
        self._resume_background_missing()

    def _add_category(self) -> None:
        """
        Show the 'Add/Append Category' dialog, write CSV rows, reload library,
        and queue missing-downloads scan.
        """

        dlg = AddCategoryDialog(self)
        if dlg.exec() == dlg.DialogCode.Accepted and dlg.rows and dlg.category:
            csv_path = append_rows_to_category_csv(dlg.category, dlg.rows)
            self.library = load_library_from_csvs()
            self._refresh_categories()

            new_cat = csv_path.stem.replace("_", " ")
            items = self.category_list.findItems(new_cat, Qt.MatchFlag.MatchExactly)
            if items:
                self.category_list.setCurrentItem(items[0])

            self._set_view_label(f"Category: {new_cat}")
            self._apply_search_now()
            self._resume_background_missing()

            themed_msg(
                self,
                QMessageBox.Icon.Information,
                "Saved",
                f"Saved {len(dlg.rows)} row(s).",
            ).exec()

    # --- View identity & base list ---------------------------------------

    def _view_identity(self) -> Tuple[str, str]:
        """
        Describe the current view as (kind, name):

        - ("favourites", "")       → favourites
        - ("playlist", playlist)   → playlist
        - ("category", category)   → normal category
        - ("category", "")         → no category selected
        """
        if self.current_category == SPECIAL_FAV_CATEGORY:
            return "favourites", ""

        if self.current_category and self.current_category.startswith(
            SPECIAL_PL_CATEGORY_PREFIX
        ):
            return "playlist", self.current_category[len(SPECIAL_PL_CATEGORY_PREFIX):]

        if self.current_category:
            return "category", self.current_category

        return "category", ""

    def _base_list_for_current_view(self) -> List[Song]:
        """
        Return the logical base song list for the current view identity.
        This is used by the search logic.
        """
        kind, name = self._view_identity()
        if kind == "favourites":
            return self._songs_from_keys(list(self.favourites))

        if kind == "playlist":
            return self._songs_from_keys(self.playlists.get(name, []))

        # Normal category view
        return self.library.get(self.current_category, [])
