from typing import List

from PyQt6.QtCore import pyqtSlot, Qt
from PyQt6.QtWidgets import (
    QTableWidgetItem,
    QMessageBox,
    QInputDialog
)

from my_player.helpers.ui_utils import themed_msg
from my_player.helpers.db_utils import save_dur_db
from my_player.helpers.file_utils import resolve_existing_file
from my_player.helpers.player_history_utils import key_str
from my_player.models.song import Song
from my_player.io.library_io import expected_path


class DownloadFileOpsMixin:
    """
    Mixin for MyPlayerMain:

    - Download progress + queue pause messages
    - Handling finished downloads (file_ready)
    - Scanning for missing files and queuing background downloads
    - Deleting downloaded files (with duration cache cleanup)
    - Refreshing (re-downloading) a song
    - Setting per-song custom URLs

    Expects the main window to provide:

      Attributes:
        self.dlm                         # DownloadManager
        self.library                     # Dict[str, List[Song]]
        self.current_list                # List[Song]
        self.current_category            # Optional[str]
        self.current_song_key            # Optional[Tuple[str,str,str,str]]
        self.last_song_key               # Optional[Tuple[str,str,str,str]]
        self.play_queue                  # List[Song]
        self.play_index                  # int
        self.play_context                # Optional[Tuple[str,str]]
        self.duration_db                 # Dict[str, int]
        self.custom_urls                 # Dict[str, str]
        self.history                     # Dict[str, dict]
        self.table                       # QTableWidget
        self.status                      # QStatusBar
        self.dl_status                   # QLabel
        self.favourites                  # set[Tuple[str,str,str,str]]
        self.playlists                   # Dict[str, List[Tuple[str,str,str,str]]]
        self._prefetch_in_progress       # bool
        self._prefetch_next_key          # Optional[Tuple[str,str,str,str]]
        self._pending_autoplay_key       # Optional[Tuple[str,str,str,str]]
        self._deferred_hi: Deque[Tuple[Song, bool]]

      Methods:
        self._save_state()
        self._set_busy(on: bool, text: str = "Working…")
        self._refresh_row_widgets(s: Song)
        self._next_global_after_key(k: Tuple[str,str,str,str]) -> Optional[Song]
        self._play_file(path, s: Song)
        self._view_identity() -> Tuple[str, str]
        self._base_list_for_current_view() -> List[Song]
        self._apply_search_now()
        self._sync_view_label_from_state()
        self._refresh_categories()
        self._rebuild_playlists_menu()
        self._populate_table_async(songs: List[Song])
        self._resume_background_missing()   # defined in this mixin, but called by others
    """

    # Column indices must match main window
    COL_FAV = 0
    COL_CATEGORY = 1
    COL_TITLE = 2
    COL_ALBUM = 3
    COL_ARTISTS = 4
    COL_DURATION = 5

    # ------------------------------------------------------------------
    # Download progress / queue pause from DownloadManager
    # ------------------------------------------------------------------

    @pyqtSlot(str, int, str, str, str)
    def _dl_progress(self, title: str, pct: int, speed: str, eta: str, category: str) -> None:
        """
        Connected to DownloadManager.progress(title, pct, speed, eta, category).
        Just updates the status label; logic unchanged.
        """
        self.dl_status.setText(f"Downloading: {title}  {pct}%  {speed}  ETA {eta}")

    @pyqtSlot(str)
    def _on_queue_paused(self, reason: str) -> None:
        """
        Called when DownloadManager pauses background queue (e.g., repeated 403).
        """
        self.status.showMessage(reason, 6000)

    # ------------------------------------------------------------------
    # Scan for missing files and enqueue background downloads
    # ------------------------------------------------------------------

    def _missing_songs(self) -> List[Song]:
        """
        Return the list of songs for which expected_path(song) does not exist.
        Pure library scan, no UI.
        """
        out: List[Song] = []
        for rows in self.library.values():
            for s in rows:
                try:
                    if not expected_path(s).exists():
                        out.append(s)
                except Exception:
                    # In case of weird path errors, just skip
                    pass
        return out

    def _resume_background_missing(self) -> None:
        """
        Resume background downloads if no high-priority jobs or active prefetch.
        Mirrors your original _resume_background_missing logic.
        """
        if self.dlm.has_high_running() or getattr(self, "_prefetch_in_progress", False):
            return

        self.dlm.resume_background()
        missing = self._missing_songs()
        if missing:
            self.dlm.enqueue_background_many(missing)
            self.status.showMessage(
                f"Background: queued {len(missing)} missing song(s).",
                3000,
            )
        else:
            self.status.showMessage("All songs present.", 1500)

    # ------------------------------------------------------------------
    # High-priority download completion handler
    # ------------------------------------------------------------------

    @pyqtSlot(object, bool, str)
    def _on_file_ready(self, song: Song, ok: bool, path_or_err: str) -> None:
        """
        Called by DownloadManager.file_ready(song, ok, path_or_err).

        If ok:
          - Refresh duration cell from cache/disk state.
          - Autoplay if this was a pending-autoplay target.
          - For prefetch: clear flags and possibly resume queued high-priority requests.

        If failed:
          - Show message only.
        """
        if ok:
            # Refresh the row widgets (duration) if visible
            self._refresh_row_widgets(song)

            k = song.key()

            # Pending autoplay?
            if self._pending_autoplay_key and self._pending_autoplay_key == k:
                self._pending_autoplay_key = None
                from pathlib import Path
                self._play_file(Path(path_or_err), song)

            # Prefetch path:
            if getattr(self, "_prefetch_in_progress", False) and self._prefetch_next_key == k:
                self._prefetch_in_progress = False
                self._prefetch_next_key = None
                self._drain_deferred_if_idle()

            self.table.viewport().update()
        else:
            self.status.showMessage(
                f"Failed: {song.title} — {path_or_err}",
                4000,
            )

        # Once any high-priority work is done, either resume pending
        # high-priority queue or background missing downloads.
        if not self.dlm.has_high_running():
            if self._deferred_hi:
                self._drain_deferred_if_idle()
            elif not getattr(self, "_prefetch_in_progress", False):
                self._resume_background_missing()

    # Helper to drain queued high-priority jobs once downloads are idle
    def _drain_deferred_if_idle(self) -> None:
        """
        Called when high-priority queue becomes idle.
        Schedules next queued high-priority job if any.
        """
        if (
            not self.dlm.has_high_running()
            and not getattr(self, "_prefetch_in_progress", False)
            and self._deferred_hi
        ):
            s, refresh = self._deferred_hi.popleft()
            self.dlm.enqueue_high(s, refresh=refresh)
            self.status.showMessage(
                f"Continuing queued high-priority: {s.title}",
                2000,
            )

    # ------------------------------------------------------------------
    # Delete / Refresh / Custom URL (context-menu actions)
    # ------------------------------------------------------------------

    def _delete_file_for_song(self, s: Song) -> None:
        """
        Delete the downloaded file, clean up duration cache entries
        (file-path + logical song key), and clear visible duration cell.
        """
        fpath = resolve_existing_file(s, migrate=True)

        # If currently playing, hop to next before deletion so player releases handle.
        if self.current_song_key and self.current_song_key == s.key():
            nxt = self._next_global_after_key(self.current_song_key)
            if nxt:
                np = resolve_existing_file(nxt, migrate=True)
                if np.exists():
                    self._play_file(np, nxt)
                else:
                    self._pending_autoplay_key = nxt.key()
                    self.dlm.enqueue_high(nxt, refresh=False)

        box = themed_msg(
            self,
            QMessageBox.Icon.Question,
            "Delete file?",
            f"Delete the downloaded file?\n\n{s.title}\n{', '.join(s.artists)}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if box.exec() != QMessageBox.StandardButton.Yes:
            return

        try:
            # Remove file
            fpath.unlink(missing_ok=True)

            # Purge duration cache under BOTH keys: logical song-key and file path
            k_song = "|".join(s.key())
            if hasattr(self, "duration_db") and isinstance(self.duration_db, dict):
                self.duration_db.pop(k_song, None)
                self.duration_db.pop(str(fpath), None)
                save_dur_db(self.duration_db)

            # Clear Duration cell in table (if visible)
            for r, row_s in enumerate(getattr(self, "current_list", [])):
                if (
                    row_s.title == s.title
                    and row_s.album == s.album
                    and row_s.category == s.category
                    and row_s.artists == s.artists
                ):
                    it = QTableWidgetItem("")
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.table.setItem(r, self.COL_DURATION, it)
                    break

            self.status.showMessage("Deleted file.", 3000)
        except Exception as e:
            themed_msg(
                self,
                QMessageBox.Icon.Critical,
                "Error",
                f"Could not delete file:\n{e}",
            ).exec()

        self._refresh_row_widgets(s)
        self.table.viewport().update()

    def _refresh_download(self, s: Song) -> None:
        """
        Force a "refresh" of the downloaded file (re-download).
        Handles:
          - Defer if a different prefetch is in progress.
          - If refreshing current song, move to next while re-downloading.
        """
        # Make progress visible immediately
        if hasattr(self, "dl_status"):
            self.dl_status.setText(f"Downloading: {s.title}  0%")
        self.status.showMessage(f"Refreshing: {s.title}", 2500)

        # If a different prefetch is running, queue this one
        if (
            getattr(self, "_prefetch_in_progress", False)
            and getattr(self, "_prefetch_next_key", None) != s.key()
        ):
            self._deferred_hi.append((s, True))
            self.status.showMessage(
                f"Queued refresh after current prefetch: {s.title}",
                2500,
            )
            return

        # If refreshing the currently playing song, move to next while re-downloading
        if self.current_song_key and self.current_song_key == s.key():
            nxt = self._next_global_after_key(self.current_song_key)
            if nxt:
                np = resolve_existing_file(nxt, migrate=True)
                if np.exists():
                    self._play_file(np, nxt)
                else:
                    self._pending_autoplay_key = nxt.key()
                    self.dlm.enqueue_high(nxt, refresh=False)

        self._pending_autoplay_key = None
        self.dlm.enqueue_high(s, refresh=True)

    def _set_custom_url_for_song(self, s: Song) -> None:
        """
        Set or clear a custom download URL for a song.
        Uses two keys:
          - exact key:  category||title||album||artists
          - base key:   *||title||album||artists
        """
        k_exact = key_str(s.key())
        k_base = key_str(("*", s.title, s.album, ", ".join(s.artists)))

        existing = self.custom_urls.get(k_exact, self.custom_urls.get(k_base, ""))

        url, ok = QInputDialog.getText(
            self,
            "Set custom source URL",
            "Paste YouTube link or direct MP3 URL:",
            text=existing,
        )
        if not ok:
            return

        url = url.strip()
        if not url:
            self.custom_urls.pop(k_exact, None)
            self.custom_urls.pop(k_base, None)
            self.status.showMessage("Custom URL cleared.", 2000)
        else:
            self.custom_urls[k_exact] = url
            self.custom_urls[k_base] = url
            self.status.showMessage("Custom URL saved.", 2000)

        self._save_state()
