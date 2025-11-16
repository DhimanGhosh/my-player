from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QMessageBox, QInputDialog

from my_player.helpers.constants import SPECIAL_PL_CATEGORY_PREFIX
from my_player.helpers.db_utils import save_dur_db
from my_player.helpers.file_utils import expected_path
from my_player.helpers.ui_utils import themed_msg
from my_player.models.song import Song
from my_player.io.library_io import load_library_from_csvs, rename_category_everywhere
from my_player.ui.theme import MaterialTheme


class ContextMenuMixin:
    def _table_context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row < 0 or row >= len(self.current_list):
            return
        s = self.current_list[row]
        menu = QMenu(self)
        menu.setStyleSheet(MaterialTheme.stylesheet())

        fav_action_text = "Remove from Favourites" if s.key() in self.favourites else "Add to Favourites"
        menu.addAction(QAction(fav_action_text, self, triggered=lambda: self._toggle_favourite(s)))

        submenu = menu.addMenu("Add to Playlist…")
        if self.playlists:
            for name in sorted(self.playlists.keys()):
                submenu.addAction(QAction(name, self, triggered=lambda _, n=name: self._add_song_to_existing_playlist_safe(s, n)))
        else:
            dummy = QAction("(No playlists yet)", self);
            dummy.setEnabled(False)
            submenu.addAction(dummy)
        submenu.addSeparator()
        submenu.addAction(QAction("New Playlist…", self, triggered=lambda: self._add_song_to_new_playlist(s)))

        if self.current_category and self.current_category.startswith(SPECIAL_PL_CATEGORY_PREFIX):
            pl_name = self.current_category[len(SPECIAL_PL_CATEGORY_PREFIX):]
            menu.addAction(QAction(f"Remove from Playlist “{pl_name}”", self,
                                   triggered=lambda: self._remove_from_playlist(s, pl_name)))

        menu.addSeparator()
        menu.addAction(QAction("↻ Refresh Download (High Priority)", self, triggered=lambda: self._refresh_download(s)))
        menu.addAction(QAction("🗑 Delete downloaded file", self, triggered=lambda: self._delete_file_for_song(s)))
        menu.addAction(QAction("Set custom source URL…", self, triggered=lambda: self._set_custom_url_for_song(s)))
        menu.addSeparator()
        menu.addAction(QAction("Move to Category…", self, triggered=lambda: self._move_or_copy_category(s, do_copy=False)))
        menu.addAction(QAction("Copy to Category…", self, triggered=lambda: self._move_or_copy_category(s, do_copy=True)))
        menu.exec(self.table.viewport().mapToGlobal(pos))


    def _player_context_menu(self, pos):
        if not (self.play_queue and 0 <= self.play_index < len(self.play_queue)):
            return
        s = self.play_queue[self.play_index]
        menu = QMenu(self)
        menu.setStyleSheet(MaterialTheme.stylesheet())
        menu.addAction(QAction("Add to Favourites", self, triggered=lambda: self._toggle_favourite_add_only(s)))
        submenu = menu.addMenu("Add to Playlist…")
        if self.playlists:
            for name in sorted(self.playlists.keys()):
                submenu.addAction(QAction(name, self, triggered=lambda _, n=name: self._add_song_to_existing_playlist_safe(s, n)))
        else:
            dummy = QAction("(No playlists yet)", self);
            dummy.setEnabled(False)
            submenu.addAction(dummy)
        submenu.addSeparator()
        submenu.addAction(QAction("New Playlist…", self, triggered=lambda: self._add_song_to_new_playlist(s)))
        menu.exec(self.sender().mapToGlobal(pos))


    def _open_category(self, name: str):
        self.current_category = name
        self.category_list.clearSelection()
        items = self.category_list.findItems(name, Qt.MatchFlag.MatchExactly)
        if items:
            self.category_list.setCurrentItem(items[0])
        self.playlist_list.clearSelection()
        self._sync_view_label_from_state()
        self._save_state()
        self._apply_search_now()


    def _category_context_menu(self, pos):
        item = self.category_list.itemAt(pos)
        if not item:
            return
        name = item.text()
        menu = QMenu(self)
        menu.setStyleSheet(MaterialTheme.stylesheet())
        menu.addAction(QAction("Open", self, triggered=lambda: self._open_category(name)))
        menu.addAction(QAction("Rename…", self,
                               triggered=lambda: self._rename_category_or_playlist(name)))
        menu.exec(self.category_list.mapToGlobal(pos))


    def _rename_category_or_playlist(self, name_or_prefixed: str):
        # ---- Playlist path (unchanged in your code) ----
        if isinstance(name_or_prefixed, str) and name_or_prefixed.startswith(SPECIAL_PL_CATEGORY_PREFIX):
            old_pl = name_or_prefixed[len(SPECIAL_PL_CATEGORY_PREFIX):]
            if not old_pl or old_pl not in self.playlists:
                themed_msg(self, QMessageBox.Icon.Information, "Not found", f"Playlist “{old_pl}” doesn’t exist.").exec()
                return
            new_pl, ok = QInputDialog.getText(self, "Rename Playlist", f"New name for playlist “{old_pl}”:")
            if not ok:
                return
            new_pl = (new_pl or "").strip()
            if not new_pl or new_pl == old_pl:
                return
            if new_pl in self.playlists:
                themed_msg(self, QMessageBox.Icon.Warning, "Already exists", f"A playlist named “{new_pl}” already exists.").exec()
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
            themed_msg(self, QMessageBox.Icon.Information, "Not found", f"Category “{old_cat}” doesn’t exist.").exec()
            return

        new_cat, ok = QInputDialog.getText(self, "Rename Category", f"New name for category “{old_cat}”:")
        if not ok:
            return
        new_cat = (new_cat or "").strip()
        if not new_cat or new_cat == old_cat:
            return
        if new_cat in self.library:
            themed_msg(self, QMessageBox.Icon.Warning, "Already exists", f"A category named “{new_cat}” already exists.").exec()
            return

        try:
            moved_pairs = rename_category_everywhere(old_cat, new_cat, self.library)
        except Exception as e:
            themed_msg(self, QMessageBox.Icon.Critical, "Rename failed", f"{e}").exec()
            return

        # Reload library to reflect new category and rows
        self.library = load_library_from_csvs()

        # Favourites
        if self.favourites:
            conv = dict(moved_pairs)
            self.favourites = {conv.get(k, k) for k in self.favourites}

        # Playlists
        if self.playlists:
            conv = dict(moved_pairs)
            for pl_name, lst in list(self.playlists.items()):
                self.playlists[pl_name] = [conv.get(k, k) for k in lst]

        # Last/current keys & view
        if self.last_song_key and self.last_song_key[0] == old_cat:
            self.last_song_key = (new_cat, self.last_song_key[1], self.last_song_key[2], self.last_song_key[3])
        if self.current_song_key and self.current_song_key[0] == old_cat:
            self.current_song_key = (new_cat, self.current_song_key[1], self.current_song_key[2], self.current_song_key[3])
        if self.current_category == old_cat:
            self.current_category = new_cat
            self._sync_view_label_from_state()

        # History
        if self.history:
            conv_hist = {"||".join(ok): "||".join(nk) for ok, nk in moved_pairs}
            self.history = {conv_hist.get(k, k): v for k, v in self.history.items()}

        # Duration cache: remap song-key entries and seed path-keys for the new locations
        if hasattr(self, "duration_db") and isinstance(self.duration_db, dict):
            conv_dur = {"|".join(ok): "|".join(nk) for ok, nk in moved_pairs}
            new_db = {conv_dur.get(k, k): v for k, v in self.duration_db.items()}
            # Ensure path-keys exist for renamed songs
            for _, nk in moved_pairs:
                s_new = Song(category=nk[0], title=nk[1], album=nk[2], artists=[x.strip() for x in nk[3].split(",") if x.strip()])
                p_new = expected_path(s_new)
                k_song = "|".join(nk)
                if k_song in new_db and str(p_new) not in new_db:
                    new_db[str(p_new)] = new_db[k_song]
            self.duration_db = new_db
            if hasattr(self, "save_dur_db"):
                self.save_dur_db(self.duration_db)
            elif "save_dur_db" in globals():
                save_dur_db(self.duration_db)

        # Custom URLs
        if self.custom_urls:
            conv_urls = {"||".join(ok): "||".join(nk) for ok, nk in moved_pairs}
            self.custom_urls = {(conv_urls.get(k, k) if not k.startswith("*||") else k): v
                                for k, v in self.custom_urls.items()}

        # Refresh UI
        self._refresh_categories()
        self._rebuild_playlists_menu()
        self._save_state()
        self._apply_search_now()
        self.status.showMessage(f"Renamed category to “{new_cat}”.", 2500)
