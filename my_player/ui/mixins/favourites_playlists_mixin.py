from typing import Dict, List, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QMessageBox,
    QInputDialog
)

from my_player.helpers.constants import (
    SPECIAL_FAV_CATEGORY,
    SPECIAL_PL_CATEGORY_PREFIX,
)
from my_player.helpers.ui_utils import themed_msg
from my_player.models.song import Song
from my_player.ui.theme import MaterialTheme


class FavouritesPlaylistsMixin:
    """
    Mixin for MyPlayerMain:

    - Favourites toggling (from table + from player)
    - Playlists (add/remove/open, left-panel + menu)
    - "Suggestions" (most played) view

    Expects the main window to provide:
      - attributes:
          self.library: Dict[str, List[Song]]
          self.favourites: set[Tuple[str,str,str,str]]
          self.playlists: Dict[str, List[Tuple[str,str,str,str]]]
          self.current_category: str | None
          self.current_list: List[Song]
          self.history: Dict[str, dict]
          self.table
          self.m_playlists
          self.m_suggest
          self.remove_pl_sel_btn
          self.status
      - methods:
          self._save_state()
          self._set_view_label(text: str)
          self._sync_view_label_from_state()
          self._apply_search_now()
          self._set_busy(on: bool, text: str = "Working…")
          self._populate_table_async(songs: List[Song])
          self._songs_from_keys(keys: List[Tuple[str,str,str,str]]) -> List[Song]
    """

    # Column indices must match main window
    COL_FAV = 0
    COL_CATEGORY = 1
    COL_TITLE = 2
    COL_ALBUM = 3
    COL_ARTISTS = 4
    COL_DURATION = 5

    # ------------------------------------------------------------------
    # Favourites
    # ------------------------------------------------------------------

    def _toggle_favourite_add_only(self, s: Song) -> None:
        k = s.key()
        if k not in self.favourites:
            self.favourites.add(k)
            self._save_state()
            self.status.showMessage("Added to favourites.", 2000)

    def _toggle_favourite_from_button(self, s: Song) -> None:
        """
        Toggle favourite for the song and refresh the "★/☆" button
        in any visible row that matches this song.
        """
        self._toggle_favourite(s)

        for r in range(self.table.rowCount()):
            title_item = self.table.item(r, self.COL_TITLE)
            album_item = self.table.item(r, self.COL_ALBUM)
            artists_item = self.table.item(r, self.COL_ARTISTS)
            category_item = self.table.item(r, self.COL_CATEGORY)

            t = title_item.text() if title_item else ""
            a = album_item.text() if album_item else ""
            ar = artists_item.text() if artists_item else ""
            c = category_item.text() if category_item else ""

            if (
                t == s.title
                and a == s.album
                and ar == ", ".join(s.artists)
                and c == s.category
            ):
                btn = self.table.cellWidget(r, self.COL_FAV)
                from PyQt6.QtWidgets import QPushButton, QToolButton

                if isinstance(btn, (QPushButton, QToolButton)):
                    btn.setText("★" if s.key() in self.favourites else "☆")
                break

    def _toggle_favourite(self, s: Song) -> None:
        """
        Toggle favourite status for a song and persist.
        """
        k = s.key()
        if k in self.favourites:
            self.favourites.remove(k)
            self.status.showMessage("Removed from favourites.", 1500)
        else:
            self.favourites.add(k)
            self.status.showMessage("Added to favourites.", 1500)

        self._save_state()

    def _show_favourites(self) -> None:
        """Switch view to 'Favourites' pseudo-category."""
        self.current_category = SPECIAL_FAV_CATEGORY
        self.category_list.clearSelection()
        self.playlist_list.clearSelection()
        self._sync_view_label_from_state()

        fav_songs = self._songs_from_keys(list(self.favourites))
        self._set_busy(True, "Rendering results…")
        self._populate_table_async(fav_songs)
        self._save_state()

    # ------------------------------------------------------------------
    # Playlists menu + left panel
    # ------------------------------------------------------------------

    def _rebuild_playlists_menu(self) -> None:
        """
        Rebuild the 'Playlists' top menu (keeps the first two actions:
        'Favourites' + separator).
        """
        actions = self.m_playlists.actions()
        for act in actions[2:]:
            self.m_playlists.removeAction(act)

        for name in sorted(self.playlists.keys()):
            self.m_playlists.addAction(
                QAction(
                    name,
                    self,
                    triggered=lambda _, n=name: self._open_playlist(n),
                )
            )

    def _open_playlist(self, name: str) -> None:
        """
        Open a playlist (as a pseudo-category) in the main view.
        """
        self.current_category = f"{SPECIAL_PL_CATEGORY_PREFIX}{name}"
        self.category_list.clearSelection()
        self.playlist_list.clearSelection()
        self._sync_view_label_from_state()

        self._set_busy(True, "Rendering results…")
        self._populate_table_async(self._songs_from_keys(self.playlists.get(name, [])))
        self._save_state()

    def _add_song_to_existing_playlist_safe(self, s: Song, name: str) -> None:
        """
        Add a song to an existing playlist, prompting if already present.
        """
        k = s.key()
        lst = self.playlists.setdefault(name, [])

        if k in lst:
            box = QMessageBox(self)
            box.setWindowTitle("Already present")
            box.setIcon(QMessageBox.Icon.Information)
            box.setTextFormat(Qt.TextFormat.PlainText)
            box.setText(f"“{s.title}” already exists in playlist “{name}”.")
            box.setStyleSheet(MaterialTheme.stylesheet())

            add_btn = box.addButton("Add anyway", QMessageBox.ButtonRole.AcceptRole)
            skip_btn = box.addButton("Skip", QMessageBox.ButtonRole.RejectRole)
            box.setDefaultButton(skip_btn)
            box.exec()

            if box.clickedButton() is not add_btn:
                self.status.showMessage("Skipped.", 1500)
                return

            lst.append(k)
        else:
            lst.append(k)
            self.status.showMessage(f"Added to playlist: {name}", 2500)

        self._save_state()
        self._rebuild_playlists_menu()
        self._refresh_playlists_panel()

    def _add_song_to_new_playlist(self, s: Song) -> None:
        """
        Prompt for a new playlist name and add the song as its first entry.
        """
        name, ok = QInputDialog.getText(self, "New Playlist", "Playlist name:")
        if not ok:
            return

        name = name.strip()
        if not name:
            return

        self._add_song_to_existing_playlist_safe(s, name)

    def _songs_from_keys(
        self, keys: List[Tuple[str, str, str, str]]
    ) -> List[Song]:
        """
        Resolve (category, title, album, artists_str) keys to Song instances
        from the in-memory library.
        """
        res: List[Song] = []
        index: Dict[str, Dict[Tuple[str, str, str], Song]] = {}

        # Build a small lookup {category: {(title, album, artists_str): Song}}
        for cat, rows in self.library.items():
            m: Dict[Tuple[str, str, str], Song] = {}
            for s in rows:
                m[(s.title, s.album, ", ".join(s.artists))] = s
            index[cat] = m

        # Resolve each key
        for k in keys:
            cat, title, album, artists_str = k
            s = index.get(cat, {}).get((title, album, artists_str))
            if s:
                res.append(s)

        return res

    def _remove_from_playlist(self, s: Song, playlist_name: str) -> None:
        """
        Remove a song from a specific playlist (if present).
        """
        k = s.key()
        lst = self.playlists.get(playlist_name, [])
        if k in lst:
            lst.remove(k)
            self._save_state()

            if self.current_category == f"{SPECIAL_PL_CATEGORY_PREFIX}{playlist_name}":
                self._set_busy(True, "Rendering results…")
                self._populate_table_async(self._songs_from_keys(lst))

            self.status.showMessage(
                f"Removed from playlist: {playlist_name}", 2500
            )

    def _remove_selected_from_current_playlist(self) -> None:
        """
        Remove selected rows from the *current* playlist view only.
        """
        if not (
            self.current_category
            and self.current_category.startswith(SPECIAL_PL_CATEGORY_PREFIX)
        ):
            return

        playlist_name = self.current_category[len(SPECIAL_PL_CATEGORY_PREFIX):]
        rows = sorted({ix.row() for ix in self.table.selectedIndexes()})
        if not rows:
            themed_msg(
                self,
                QMessageBox.Icon.Information,
                "Nothing selected",
                "Select one or more rows to remove.",
            ).exec()
            return

        keys_to_remove: List[Tuple[str, str, str, str]] = []
        for r in rows:
            if 0 <= r < len(self.current_list):
                s = self.current_list[r]
                keys_to_remove.append(s.key())

        lst = self.playlists.get(playlist_name, [])
        changed = False
        for k in keys_to_remove:
            if k in lst:
                lst.remove(k)
                changed = True

        if changed:
            self._save_state()
            self._set_busy(True, "Rendering results…")
            self._populate_table_async(self._songs_from_keys(lst))
            self.status.showMessage(
                f"Removed {len(keys_to_remove)} song(s) from playlist: {playlist_name}",
                3000,
            )
