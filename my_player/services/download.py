import threading
import queue
import subprocess
import sys
import time
import re
import os

from typing import Dict, List, Optional, Tuple
from pathlib import Path

from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from my_player.helpers.constants import BAD_SEARCH_KEYWORDS, MIN_SEC, MAX_SEC
from my_player.models.song import Song
from my_player.helpers.file_utils import expected_path
from my_player.models.download import DownloadJob


class DownloadManager(QObject):
    file_ready = pyqtSignal(object, bool, str)  # song, ok, path_or_err
    progress   = pyqtSignal(str, int, str, str, str)  # title, pct, speed, eta, category
    queue_paused = pyqtSignal(str)  # reason message

    def __init__(self, parent=None, bg_concurrency=4, custom_map: Optional[Dict[str, str]]=None, history=None):
        super().__init__(parent)
        self._custom = custom_map or {}
        self._history = history or {}

        self._stop = False
        self._high_q: queue.Queue[DownloadJob] = queue.Queue()
        self._bg_q: queue.Queue[DownloadJob] = queue.Queue()
        self._bg_enabled = False

        # Repeat-403 guard
        self._recent_403 = 0
        self._last_403_ts = 0.0
        self._pause_until = 0.0  # epoch seconds

        self._hi_workers: List[threading.Thread] = []
        self._bg_workers: List[threading.Thread] = []
        self._spawn_workers(hi=2, bg=bg_concurrency)

        # Housekeeping timer (on Qt thread) just to emit throttled progress from workers if needed
        self._pulse = QTimer(self)
        self._pulse.setInterval(1000)
        self._pulse.timeout.connect(lambda: None)
        self._pulse.start()

    # ---------- public ----------
    def enqueue_high(self, song: Song, refresh: bool):
        self._high_q.put(DownloadJob(song=song, refresh=refresh, high=True))

    def enqueue_background_many(self, songs: List[Song]):
        for s in songs:
            self._bg_q.put(DownloadJob(song=s, refresh=False, high=False))

    def resume_background(self):
        self._bg_enabled = True

    def pause_background(self):
        self._bg_enabled = False

    def has_high_running(self) -> bool:
        return not self._high_q.empty()

    # ---------- workers ----------
    def _spawn_workers(self, hi: int, bg: int):
        for _ in range(hi):
            t = threading.Thread(target=self._worker_loop, args=(self._high_q, True), daemon=True)
            t.start(); self._hi_workers.append(t)
        for _ in range(bg):
            t = threading.Thread(target=self._worker_loop, args=(self._bg_q, False), daemon=True)
            t.start(); self._bg_workers.append(t)

    def _worker_loop(self, q: queue.Queue[DownloadJob], is_high: bool):
        while not self._stop:
            try:
                job: DownloadJob = q.get(timeout=0.25)
            except queue.Empty:
                continue

            # Respect queue pause after too many 403s
            if time.time() < self._pause_until:
                time.sleep(0.5)
                q.put(job)  # requeue
                continue

            if (not is_high) and (not self._bg_enabled):
                time.sleep(0.2)
                q.put(job)
                continue

            s = job.song
            outp = expected_path(s)

            try:
                # Skip if already present and not refresh
                if outp.exists() and not job.refresh:
                    self.file_ready.emit(s, True, str(outp))
                    continue

                self.progress.emit(s.title, 0, "", "", s.category)  # let UI show that it started
                ok, msg = self._download_song_file(s, str(outp))
                if ok:
                    self.file_ready.emit(s, True, str(outp))
                else:
                    self.file_ready.emit(s, False, msg)

            except Exception as e:
                self.file_ready.emit(s, False, str(e))
            finally:
                q.task_done()

    # ---------- yt-dlp wrapper ----------
    def _download_song_file(self, s: Song, out_path: str) -> Tuple[bool, str]:
        """
        Prefer exact/wildcard custom URL; otherwise search with tight filters to avoid jukeboxes.
        Emits early progress via self.progress for better UI feedback.
        """
        # Let UI know immediately
        try:
            self.progress.emit(s.title, 0, "", "", s.category)
        except Exception:
            pass

        # Pick source (custom URL first)
        key_exact = "||".join(s.key())
        key_wild  = "||".join(("*", s.title, s.album, ", ".join(s.artists)))
        if hasattr(self, "_custom") and key_exact in self._custom:
            source = self._custom[key_exact]
        elif hasattr(self, "_custom") and key_wild in self._custom:
            source = self._custom[key_wild]
        else:
            source = f"ytsearch1:{s.title} {', '.join(s.artists)} {s.album}".strip()

        Path(os.path.dirname(out_path)).mkdir(parents=True, exist_ok=True)

        rej = "|".join(re.escape(k) for k in (BAD_SEARCH_KEYWORDS or []))
        cmd = [
            sys.executable, "-m", "yt_dlp",
            "--no-playlist",
            "-f", "bestaudio/best",
            "-x", "--audio-format", "mp3",
            "-o", out_path,
            "--retry-sleep", "1",
            "--concurrent-fragments", "1",
            "--match-filter", f"duration < {MAX_SEC} & duration > {MIN_SEC}",
        ]
        if rej:
            cmd += ["--reject-title", rej]
        cmd.append(source)

        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except Exception as e:
            return False, str(e)

        if proc.returncode == 0 and Path(out_path).exists():
            return True, "ok"

        err = (proc.stderr or proc.stdout or "").strip()
        return False, (err[:500] if err else "Download failed")
