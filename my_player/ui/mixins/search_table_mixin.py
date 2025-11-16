from typing import List

from PyQt6.QtCore import Qt, QTimer, QThreadPool, pyqtSlot
from PyQt6.QtWidgets import QTableWidgetItem, QToolButton

from my_player.models.song import Song
from my_player.services.search import SearchTask
from my_player.helpers.constants import TABLE_BATCH_SIZE


class SearchTableMixin:
    """
    Handles:
      - search scope ("Category" / "Global")
      - debounced search dispatch to SearchTask
      - async table population in small batches (to keep UI responsive)
      - sorting (column click, persistent sort state)

    Expects the main window to provide:
      - widgets:
          self.table
          self.search_edit
          self.scope_combo
          self.no_results_hint
          self.status
      - state:
          self.library: Dict[str, List[Song]]
          self.current_category: Optional[str]
          self.current_list: List[Song]
          self.favourites: set[tuple]
          self.duration_db: dict
          self.sort_col: Optional[int]
          self.sort_asc: bool
          self._search_seq: int
          self._last_search_seq: int
          self._search_running: bool
          self._populate_timer: Optional[QTimer]
          self._populate_source: List[Song]
          self._populate_index: int
          self._populate_gen: int
      - helpers:
          self._set_busy(on: bool, text: str = "Working…")
          self._base_list_for_current_view() -> List[Song]
          self._highlight_playing_row_if_visible(animated: bool = False)
          self._save_state()
    """

    # Column indices (must match other mixins & main window)
    COL_FAV = 0
    COL_CATEGORY = 1
    COL_TITLE = 2
    COL_ALBUM = 3
    COL_ARTISTS = 4
    COL_DURATION = 5

    # ------------------------------------------------------------------
    # Scope + search trigger
    # ------------------------------------------------------------------

    def _current_scope(self) -> str:
        return self.scope_combo.currentText() if self.scope_combo else "Category"

    def _apply_search_now(self):
        """
        Triggers search or fast-path render. Safe to call repeatedly; it cancels
        any pending batch population first.
        """
        query = (self.search_edit.text() if self.search_edit else "").strip()
        scope = self._current_scope()

        # Cancel any row population in progress cleanly.
        self._cancel_async_population()

        self._search_seq += 1
        self._last_search_seq = self._search_seq
        self._search_running = True

        base_for_view = self._base_list_for_current_view()

        # Fast path: blank query in Category scope → just render current view, sorted
        if scope == "Category" and not query:
            self._set_busy(True, "Rendering…")
            songs = self._apply_sort_to_songs(list(base_for_view))
            self._populate_table_async(songs)
            return

        # General async search path (SearchTask already runs in QThreadPool)
        self._set_busy(True, "Searching…")
        task = SearchTask(
            seq=self._search_seq,
            mode=scope,
            query=query,
            library=self.library,
            base_list=base_for_view,
        )
        task.signals.done.connect(self._on_search_results)
        QThreadPool.globalInstance().start(task)

    @pyqtSlot(int, object)
    def _on_search_results(self, seq: int, songs_obj: object):
        """
        Callback from SearchTask once it finishes.
        """
        if seq != self._last_search_seq:
            # Out-of-date result; ignore
            return

        self._search_running = False
        songs: List[Song] = list(songs_obj) if songs_obj else []
        songs = self._apply_sort_to_songs(songs)

        self.status.showMessage(f"Found {len(songs)} item(s).", 1500)
        self._set_busy(True, "Rendering results…")
        self._populate_table_async(songs)

    # ------------------------------------------------------------------
    # Async table population (batch insert)
    # ------------------------------------------------------------------

    def _cancel_async_population(self):
        if getattr(self, "_populate_timer", None):
            try:
                self._populate_timer.timeout.disconnect(self._populate_step)
            except Exception:
                pass
            self._populate_timer.stop()
            self._populate_timer.deleteLater()

        self._populate_timer = None
        self._populate_source = []
        self._populate_index = 0

    def _populate_table_async(self, songs: List[Song]):
        """
        Prepare for incremental population (small batches) so the UI and audio remain responsive.
        """
        self._cancel_async_population()

        self.current_list = songs
        self.table.setSortingEnabled(False)
        self.table.clearContents()
        self.table.setRowCount(0)
        self.table.setUpdatesEnabled(False)

        if not songs:
            self.no_results_hint.show()
        else:
            self.no_results_hint.hide()

        self._populate_source = list(songs)
        self._populate_index = 0

        # Fire the timer as fast as the event loop allows; TABLE_BATCH keeps it light.
        self._populate_timer = QTimer(self)
        self._populate_timer.setInterval(0)  # immediate, but each step inserts a small batch
        self._populate_timer._gen = getattr(self, "_populate_gen", 0) + 1
        self._populate_gen = self._populate_timer._gen
        self._populate_timer.timeout.connect(self._populate_step)
        self._populate_timer.start()

    def _populate_step(self):
        """
        Incrementally populate the table with rows from self._populate_source.
        Runs as a timer-driven batch to keep the UI responsive.
        """
        t = self._populate_timer
        if not t:
            return

        # If a newer populate cycle started, stop this one.
        cur_gen = getattr(t, "_gen", None)
        if cur_gen != self._populate_gen:
            t.stop()
            return

        src = self._populate_source
        n = len(src)

        # Finished?
        if self._populate_index >= n:
            self.table.resizeRowsToContents()
            self.table.setUpdatesEnabled(True)
            self._cancel_async_population()
            self._highlight_playing_row_if_visible()
            self._set_busy(False)
            return

        end = min(self._populate_index + TABLE_BATCH_SIZE, n)

        for i in range(self._populate_index, end):
            s = src[i]
            row = self.table.rowCount()
            self.table.insertRow(row)

            # --- Fav star button (kept inside its cell)
            fav_btn = QToolButton()
            fav_btn.setText("★" if s.key() in self.favourites else "☆")
            fav_btn.setToolTip("Toggle favourite")
            fav_btn.setFixedSize(28, 22)
            fav_btn.setAutoRaise(True)
            fav_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)

            from functools import partial

            fav_btn.clicked.connect(partial(self._toggle_favourite_from_button, s))
            self.table.setCellWidget(row, self.COL_FAV, fav_btn)

            # --- Text cells
            self.table.setItem(row, self.COL_CATEGORY, QTableWidgetItem(s.category))
            self.table.setItem(row, self.COL_TITLE, QTableWidgetItem(s.title))
            self.table.setItem(row, self.COL_ALBUM, QTableWidgetItem(s.album))
            self.table.setItem(row, self.COL_ARTISTS, QTableWidgetItem(", ".join(s.artists)))

            # --- Duration (cache-only; always mm:ss)
            dur_txt = "—"
            sec = self._cached_seconds(s)
            if sec is not None:
                dur_txt = self._mmss_from_seconds(sec)
            dur_item = QTableWidgetItem(dur_txt)
            dur_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, self.COL_DURATION, dur_item)

        self._populate_index = end

    def _update_empty_hint(self):
        self.empty_hint.setVisible(self.table.rowCount() == 0)

    def _refresh_row_widgets(self, s: Song):
        """
        Refresh only the visible row(s) that correspond to `s`.
        Uses cache-only (no disk scans), and always formats as mm:ss.
        """
        # Build the formatted duration text from cache
        dur_txt = "—"
        sec = self._cached_seconds(s)
        if sec is not None:
            dur_txt = self._mmss_from_seconds(sec)

        # Update any visible row that matches this song
        for r in range(self.table.rowCount()):
            t = self.table.item(r, self.COL_TITLE).text()    if self.table.item(r, self.COL_TITLE)    else ""
            a = self.table.item(r, self.COL_ALBUM).text()    if self.table.item(r, self.COL_ALBUM)    else ""
            ar= self.table.item(r, self.COL_ARTISTS).text()  if self.table.item(r, self.COL_ARTISTS)  else ""
            c = self.table.item(r, self.COL_CATEGORY).text() if self.table.item(r, self.COL_CATEGORY) else ""
            if (t == (s.title or "") and
                a == (s.album or "") and
                ar == ", ".join(s.artists or []) and
                c == (s.category or "")):
                it = QTableWidgetItem(dur_txt)
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(r, self.COL_DURATION, it)

    # ------------------------------------------------------------------
    # Sorting
    # ------------------------------------------------------------------

    def _apply_sort_to_songs(self, songs: List[Song]) -> List[Song]:
        if self.sort_col is None:
            return list(songs)

        def key_fn(s: Song):
            if self.sort_col == self.COL_FAV:
                return (s.key() not in self.favourites, s.title.lower())
            if self.sort_col == self.COL_CATEGORY:
                return s.category.lower()
            if self.sort_col == self.COL_TITLE:
                return s.title.lower()
            if self.sort_col == self.COL_ALBUM:
                return s.album.lower()
            if self.sort_col == self.COL_ARTISTS:
                return ", ".join(s.artists).lower()
            if self.sort_col == self.COL_DURATION:
                # IMPORTANT: cache-only; avoid filesystem during sort.
                sec = self.duration_db.get("|".join(s.key()))
                return float("inf") if sec is None else int(sec)
            return 0

        return sorted(songs, key=key_fn, reverse=not self.sort_asc)

    def _on_header_clicked(self, col: int):
        """
        Sort handler that does NOT trigger a fresh search. It simply re-sorts the
        current working list (or base list when current_list is empty) and re-renders
        in small batches to stay responsive.
        """
        # Toggle / set sort
        if self.sort_col == col:
            self.sort_asc = not self.sort_asc
        else:
            self.sort_col = col
            self.sort_asc = True

        # Reflect arrow state
        self.table.horizontalHeader().setSortIndicator(
            col,
            Qt.SortOrder.AscendingOrder if self.sort_asc else Qt.SortOrder.DescendingOrder,
        )

        # Persist user choice
        self._save_state()

        # Choose the source to sort: currently shown results if present,
        # else the base list for the current view (category/playlist/favourites).
        if self.current_list:
            base = list(self.current_list)
        else:
            base = list(self._base_list_for_current_view())

        # Apply the new sort order and re-render incrementally.
        songs = self._apply_sort_to_songs(base)
        self._set_busy(True, "Sorting…")
        self._populate_table_async(songs)
