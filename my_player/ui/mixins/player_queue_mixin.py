from typing import List, Optional, Tuple
from pathlib import Path

from PyQt6.QtCore import (
    Qt,
    QTimer,
    QEasingCurve,
    QAbstractAnimation,
    QPropertyAnimation,
    pyqtSlot
)
from PyQt6.QtWidgets import QTableWidgetItem
from PyQt6.QtMultimedia import QMediaPlayer

from my_player.helpers.constants import PREFETCH_MS
from my_player.helpers.duration_utils import ms_to_mmss
from my_player.helpers.db_utils import save_dur_db
from my_player.helpers.file_utils import resolve_existing_file
from my_player.helpers.player_history_utils import key_str
from my_player.models.song import Song


class PlayerQueueMixin:
    """
    Handles:
      - Playing a selected song (from table / queue)
      - Global play/pause button logic
      - Next / previous song (with category wrapping)
      - Global-next logic across categories
      - Seekbar + time label
      - Duration cache (mixed ms/sec normalization, cached lookups)
      - Animated scroll to playing row
      - Prefetching next song when T-60s
      - Volume changes

    Expects the main window to provide:
      - widgets:
          self.table
          self.seek
          self.time_label
          self.playpause_btn
          self.prev_btn
          self.next_btn
          self.vol_label
          self.vol_slider
          self.cur_info
          self.status
          self.dl_status
      - Qt objects:
          self.player: QMediaPlayer
          self.audio_output: QAudioOutput
          self.dlm: DownloadManager
      - state:
          self.library: Dict[str, List[Song]]
          self.current_category: Optional[str]
          self.current_list: List[Song]
          self.duration_db: dict
          self.history: dict
          self.current_song_key: Optional[Tuple[str,str,str,str]]
          self.last_song_key: Optional[Tuple[str,str,str,str]]
          self.play_queue: List[Song]
          self.play_index: int
          self.play_context: Optional[Tuple[str,str]]
          self._user_seeking: bool
          self._duration_ms: int
          self._prefetch_triggered: bool
          self._prefetch_in_progress: bool
          self._prefetch_next_key: Optional[Tuple[str,str,str,str]]
          self._pending_autoplay_key: Optional[Tuple[str,str,str,str]]
          self._deferred_hi: "deque[Tuple[Song,bool]]"
      - helpers:
          self._set_busy(on: bool, text: str = "Working…")
          self._view_identity() -> Tuple[str,str]
          self._base_list_for_current_view() -> List[Song]
          self._apply_search_now()
          self._save_state()
          self._resume_background_missing()
    """

    # ------------------------------------------------------------------
    # Public trigger from table double-click
    # ------------------------------------------------------------------

    def _play_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0 and self.table.rowCount() > 0:
            row = 0
        if row >= 0:
            self._start_playback_from_row(row)

    # ------------------------------------------------------------------
    # Core "play a file" logic
    # ------------------------------------------------------------------

    def _play_file(self, path: Path, s: Song) -> None:
        """
        Called once a usable media file path is known for a Song.
        Sets up QMediaPlayer, updates history, and highlights the row.
        """
        # Reset prefetch state
        self._prefetch_triggered = False
        self._prefetch_in_progress = False
        self._prefetch_next_key = None
        self._pending_autoplay_key = None

        self.current_song_key = s.key()

        try:
            p = path.resolve(strict=False)
        except Exception:
            p = path

        # Always use absolute file:// URL
        from PyQt6.QtCore import QUrl

        self.player.setSource(QUrl.fromLocalFile(str(p)))
        self.player.play()
        self._set_play_icon(True)
        self.cur_info.setText(f"Playing: {s.title} — {', '.join(s.artists)}")

        # Update history
        ks = key_str(self.current_song_key)
        info = self.history.get(ks, {"plays": 0, "channels": {}})
        info["plays"] = int(info.get("plays", 0)) + 1
        self.history[ks] = info
        self._save_state()

        self._highlight_playing_row_if_visible(animated=False)

    def _set_play_icon(self, playing: bool) -> None:
        """
        Update play/pause button label.
        """
        self.playpause_btn.setText("Pause" if playing else "Play")

    # ------------------------------------------------------------------
    # Global Play/Pause button behavior
    # ------------------------------------------------------------------

    def _toggle_playpause(self) -> None:
        st = self.player.playbackState()
        if st == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self._set_play_icon(False)
            return

        src = self.player.source()
        if src and src.isLocalFile():
            self.player.play()
            self._set_play_icon(True)
            return

        # Nothing loaded yet; decide what to play
        if self.table.rowCount() == 0 or not self.current_list:
            if not self.current_category:
                # Try last category from state
                if self.last_song_key:
                    self._open_category_silent(self.last_song_key[0])
                else:
                    cats = sorted(self.library.keys())
                    if cats:
                        self._open_category_silent(cats[0])

            # Re-enter once view is ready
            QTimer.singleShot(0, self._toggle_playpause)
            return

        # Try to restore last song row
        row = self.table.currentRow()
        if row < 0 and self.last_song_key and self.current_category == self.last_song_key[0]:
            row = self._select_row_for_song_key(self.last_song_key)

        if row < 0 and self.table.rowCount() > 0:
            row = 0
            self.table.selectRow(row)

        if row >= 0:
            self._play_selected()

    # ------------------------------------------------------------------
    # Selecting a row by Song key
    # ------------------------------------------------------------------

    def _select_row_for_song_key(self, k: Tuple[str, str, str, str]) -> int:
        if not k:
            return -1

        _, title, album, artists_str = k
        for r in range(self.table.rowCount()):
            t_item = self.table.item(r, self.COL_TITLE)
            a_item = self.table.item(r, self.COL_ALBUM)
            ar_item = self.table.item(r, self.COL_ARTISTS)

            t = t_item.text() if t_item else ""
            a = a_item.text() if a_item else ""
            ar = ar_item.text() if ar_item else ""

            if t == title and a == album and ar == artists_str:
                return r

        return -1

    def _open_category_silent(self, name: str) -> None:
        """
        Change current_category and re-render, but skip list selection tweaks.
        Used when resuming from last song/category.
        """
        self.current_category = name
        self._sync_view_label_from_state()
        self._apply_search_now()

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------

    def _start_playback_from_row(self, row: int) -> None:
        if row < 0 or row >= len(self.current_list):
            return

        # Queue = current list
        self.play_queue = list(self.current_list)
        self.play_index = row
        self.play_context = self._view_identity()

        s = self.play_queue[self.play_index]
        p = resolve_existing_file(s, migrate=True)
        if not p.exists():
            # No file: enqueue high-priority download and remember target
            self._pending_autoplay_key = s.key()
            self.dlm.enqueue_high(s, refresh=False)
            self.status.showMessage(f"Queued (high): {s.title}", 1500)
            return

        self._play_file(p, s)

    def _all_songs_global_in_order(self) -> List[Song]:
        """
        Flat list of all songs, ordered by category name then rows.
        Used for global-next after leaving the last song in a category.
        """
        out: List[Song] = []
        for cat in sorted(self.library.keys(), key=lambda x: x.lower()):
            out.extend(self.library.get(cat, []))
        return out

    def _next_global_after_key(
        self, k: Tuple[str, str, str, str]
    ) -> Optional[Song]:
        """
        Given a song key, compute the next song in the global sequence
        (category-by-category).
        """
        all_songs = self._all_songs_global_in_order()
        if not all_songs:
            return None

        for i, s in enumerate(all_songs):
            if s.key() == k:
                return all_songs[(i + 1) % len(all_songs)]

        return all_songs[0]

    def _next_in_queue_index(self) -> Optional[int]:
        """
        Compute the next index inside the *current* play_queue, handling
        wrap-around and category-to-category transitions.
        """
        if not self.play_queue:
            return None

        if self.play_index < 0:
            return 0

        nxt = self.play_index + 1
        if nxt < len(self.play_queue):
            return nxt

        # Wrapped at end of current category list
        kind, name = self._view_identity()
        if kind != "category" or not name:
            return 0

        cats = sorted(self.library.keys())
        if not cats:
            return 0

        try:
            i = cats.index(name)
        except ValueError:
            i = -1

        next_cat = cats[(i + 1) % len(cats)]
        self._open_category_silent(next_cat)
        base = list(self.library.get(next_cat, []))
        self.play_queue = base
        self.play_context = ("category", next_cat)
        self.play_index = -1
        return 0

    def _prev_in_queue_index(self) -> Optional[int]:
        if not self.play_queue:
            return None
        if self.play_index < 0:
            return 0
        return (self.play_index - 1) % len(self.play_queue)

    # ------------------------------------------------------------------
    # Next / Previous buttons
    # ------------------------------------------------------------------

    def _next_song(self) -> None:
        idx = self._next_in_queue_index()
        if idx is not None and self.play_queue:
            # If wrapping to 0, jump to global next (category-to-category)
            if (
                (self.play_index + 1) % len(self.play_queue) == 0
                and self.current_song_key
            ):
                s = self._next_global_after_key(self.current_song_key)
                if s:
                    p = resolve_existing_file(s, migrate=True)
                    if p.exists():
                        self.play_queue = [s]
                        self.play_index = 0
                        self.play_context = ("category", s.category)
                        self._play_file(p, s)
                    else:
                        self._pending_autoplay_key = s.key()
                        self.dlm.enqueue_high(s, refresh=False)
                    return

            # Normal next inside the queue
            self.play_index = idx
            s = self.play_queue[self.play_index]
            p = resolve_existing_file(s, migrate=True)
            if p.exists():
                self._play_file(p, s)
            else:
                self._pending_autoplay_key = s.key()
                self.dlm.enqueue_high(s, refresh=False)

    def _prev_song(self) -> None:
        idx = self._prev_in_queue_index()
        if idx is None:
            return

        self.play_index = idx
        s = self.play_queue[self.play_index]
        p = resolve_existing_file(s, migrate=True)
        if p.exists():
            self._play_file(p, s)
        else:
            self._pending_autoplay_key = s.key()
            self.dlm.enqueue_high(s, refresh=False)

    # ------------------------------------------------------------------
    # Prefetch logic + media status
    # ------------------------------------------------------------------

    def _start_next_prefetch(self) -> None:
        """
        When remaining time <= PREFETCH_MS, start high-priority download
        of the next song if the file does not exist yet.
        """

        if self._prefetch_triggered:
            return

        idx = self._next_in_queue_index()
        if idx is None or not self.play_queue:
            return

        nxt = self.play_queue[idx]
        p = resolve_existing_file(nxt, migrate=False)
        if p.exists():
            self._prefetch_triggered = True
            self._prefetch_in_progress = False
            self._prefetch_next_key = nxt.key()
            return

        self._prefetch_triggered = True
        self._prefetch_in_progress = True
        self._prefetch_next_key = nxt.key()
        self.dlm.enqueue_high(nxt, refresh=False)
        self.status.showMessage(f"Prefetching next (T–60s): {nxt.title}", 2500)

    def _on_media_status(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._next_song()

        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._set_play_icon(True)
        else:
            self._set_play_icon(False)

    # ------------------------------------------------------------------
    # Position / Seek handling
    # ------------------------------------------------------------------

    @pyqtSlot("qint64")
    def _on_pos_changed(self, pos_ms: int) -> None:
        if not self._user_seeking:
            self.seek.setValue(pos_ms)

        self.time_label.set_times(
            ms_to_mmss(pos_ms), ms_to_mmss(self._duration_ms)
        )

        if (
            self._duration_ms > 0
            and (self._duration_ms - pos_ms) <= PREFETCH_MS
            and not self._prefetch_triggered
        ):
            self._start_next_prefetch()

    @pyqtSlot("qint64")
    def _on_duration_changed(self, dur_ms: int) -> None:
        """
        Track and cache duration for the *currently playing* song.
        Preserves your ms/sec mixed cache semantics.
        """
        self._duration_ms = max(0, dur_ms)
        self.seek.setRange(0, max(1, self._duration_ms))
        self.time_label.set_times(
            ms_to_mmss(self.player.position()), ms_to_mmss(self._duration_ms)
        )

        src = self.player.source()
        if src and src.isLocalFile() and dur_ms > 0:
            p = src.toLocalFile()
            secs = int(dur_ms // 1000)

            # Store under file-path key and logical song-key
            self.duration_db[p] = secs
            if self.current_song_key:
                k1 = "|".join(self.current_song_key)
                self.duration_db[k1] = secs
            save_dur_db(self.duration_db)

            # Update Duration cell for visible row of playing song
            for r, s in enumerate(self.current_list):
                sp = resolve_existing_file(s, migrate=False)
                if str(sp) == p or (
                    self.current_song_key
                    and "|".join(s.key()) == "|".join(self.current_song_key)
                ):
                    it = QTableWidgetItem(self._mmss_from_seconds(secs))
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    self.table.setItem(r, self.COL_DURATION, it)
                    break

    # --- Duration helpers -------------------------------------------------

    def _sec_from_cache_val(self, val) -> Optional[int]:
        """
        Return duration in seconds from mixed cache (seconds or milliseconds).
        Mirrors your original logic.
        """
        try:
            v = int(val)
        except Exception:
            return None

        # If value looks like milliseconds (>= 60,000) and converts to
        # a plausible length (< 12h), treat as ms→s.
        if v >= 60_000:
            v2 = v // 1000
            if 0 < v2 < 12 * 3600:
                return v2

        # If already seconds but implausibly huge (>12h), ignore.
        if v <= 0 or v >= 12 * 3600:
            return None

        return v

    def _cached_seconds(self, s: Song) -> Optional[int]:
        """
        Return cached seconds for a song, checking both song-key and file-path keys.
        """
        try:
            k1 = "|".join(s.key())
            if k1 in self.duration_db:
                sec = self._sec_from_cache_val(self.duration_db[k1])
                if sec is not None:
                    return sec

            p = resolve_existing_file(s, migrate=True)
            sp = str(p)
            if sp in self.duration_db:
                sec = self._sec_from_cache_val(self.duration_db[sp])
                if sec is not None:
                    return sec
        except Exception:
            pass

        return None

    def _mmss_from_seconds(self, sec: int) -> str:
        m = max(0, sec) // 60
        s = max(0, sec) % 60
        return f"{m:02d}:{s:02d}"

    # --- Seeking ----------------------------------------------------------

    def _on_seek_start(self) -> None:
        self._user_seeking = True

    def _on_seek_preview(self, value: int) -> None:
        self.time_label.set_times(
            ms_to_mmss(value), ms_to_mmss(self._duration_ms)
        )

    def _on_seek_commit(self) -> None:
        self.player.setPosition(self.seek.value())
        self._user_seeking = False

    # --- Volume -----------------------------------------------------------

    def _on_volume_changed(self, value: int) -> None:
        """
        Slider → QAudioOutput volume and label update.
        Also persisted via _save_state (vol is stored in STATE_DB).
        """
        self.audio_output.setVolume(max(0.0, min(1.0, value / 100.0)))
        self.vol_label.setText(f"Vol: {value}%")
        self._save_state()

    # ------------------------------------------------------------------
    # Scrolling + row highlight
    # ------------------------------------------------------------------

    def _animate_scroll_to_row(self, row: int) -> None:
        if row < 0:
            return

        bar = self.table.verticalScrollBar()
        row_y = self.table.rowViewportPosition(row)
        row_h = self.table.rowHeight(row)
        view_h = self.table.viewport().height()
        target_value = row_y - max(0, (view_h // 2 - row_h // 2))
        target_value = max(0, min(target_value, bar.maximum()))

        anim = QPropertyAnimation(bar, b"value", self)
        anim.setDuration(220)
        anim.setStartValue(bar.value())
        anim.setEndValue(target_value)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)

    def _highlight_playing_row_if_visible(self, animated: bool = False) -> None:
        """
        Ensure the currently playing song row is highlighted when the
        view identity matches the play_context (e.g., same category).
        """
        if not self.play_queue or not (0 <= self.play_index < len(self.play_queue)):
            self.table.viewport().update()
            return

        if self.play_context == self._view_identity():
            playing = self.play_queue[self.play_index]
            row = -1
            for r in range(self.table.rowCount()):
                t_item = self.table.item(r, self.COL_TITLE)
                a_item = self.table.item(r, self.COL_ALBUM)
                ar_item = self.table.item(r, self.COL_ARTISTS)
                c_item = self.table.item(r, self.COL_CATEGORY)

                t = t_item.text() if t_item else ""
                a = a_item.text() if a_item else ""
                ar = ar_item.text() if ar_item else ""
                c = c_item.text() if c_item else ""

                if (
                    t == playing.title
                    and a == playing.album
                    and ar == ", ".join(playing.artists)
                    and c == playing.category
                ):
                    row = r
                    break

            if animated and row >= 0:
                self._animate_scroll_to_row(row)

        self.table.viewport().update()
