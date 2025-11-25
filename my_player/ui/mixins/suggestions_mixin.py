from typing import List, Tuple

from PyQt6.QtGui import QAction

from my_player.models.song import Song
from my_player.ai.suggestion_engine import SuggestionEngine


class SuggestionsMixin:
    """
    Mixin for “Suggestions / Most played + AI” logic and menu.

    Expects the main window to provide:

      Attributes:
        self.m_suggest                  # QMenu (Suggestions menu)
        self.history: Dict[str, dict]   # play history, keyed by "||".join(song.key())
        self.current_category

      Methods:
        self._songs_from_keys(keys: List[Tuple[str,str,str,str]]) -> List[Song]
        self._set_view_label(text: str) -> None
        self._set_busy(on: bool, text: str = "Working…") -> None
        self._populate_table_async(songs: List[Song]) -> None
    """

    def _rebuild_suggestions_menu(self) -> None:
        """
        Rebuild the “Suggestions” menu.
        """
        self.m_suggest.clear()
        self.m_suggest.addAction(
            QAction("Show Top Suggestions", self, triggered=self._show_suggestions)
        )

    def _show_suggestions(self) -> None:
        """
        Show suggestions using AI / ML:

        - Learn from play history (what I play most + recency).
        - Suggest most-played local songs.
        - Plus NEW songs from the internet matching artists / language patterns.
        """
        if not getattr(self, "history", None):
            self._set_view_label("Suggestions (No history yet)")
            return

        # Build Song objects for everything that has ever appeared in history.
        all_keys: List[Tuple[str, str, str, str]] = [
            tuple(k.split("||")) for k in self.history.keys()
        ]
        all_songs: List[Song] = self._songs_from_keys(all_keys)

        engine = SuggestionEngine(history=self.history, all_songs=all_songs)

        # 1) Local suggestions: most played + recency-weighted
        local_songs: List[Song] = engine.build_local_suggestions(limit=200)

        # 2) Online suggestions: new songs from YouTube in similar artist / language space
        external_songs: List[Song] = engine.build_external_suggestions(
            max_external=50
        )

        # Merge, keeping order: local first, then online
        songs: List[Song] = local_songs + external_songs

        self.current_category = None
        self._set_view_label("Suggestions (AI)")
        self._set_busy(True, "Rendering results…")
        self._populate_table_async(songs)
