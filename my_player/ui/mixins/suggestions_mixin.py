from typing import List, Tuple

from PyQt6.QtGui import QAction

from my_player.models.song import Song


class SuggestionsMixin:
    """
    Mixin for “Suggestions / Most played” logic and menu.

    Expects the main window to provide:

      Attributes:
        self.m_suggest              # QMenu (Suggestions menu)
        self.history: Dict[str, dict]
        self.current_category
      Methods:
        self._songs_from_keys(keys: List[Tuple[str,str,str,str]]) -> List[Song]
        self._set_view_label(text: str) -> None
        self._set_busy(on: bool, text: str = "Working…") -> None
        self._populate_table_async(songs: List[Song]) -> None
    """

    def _rebuild_suggestions_menu(self) -> None:
        """
        Rebuild the “Suggestions” menu. Logic same as original.
        """
        self.m_suggest.clear()
        self.m_suggest.addAction(
            QAction("Show Top Suggestions", self, triggered=self._show_suggestions)
        )

    def _show_suggestions(self) -> None:
        """
        Show 'Suggestions (Most Played)' view based on self.history["plays"].
        """
        counts: List[Tuple[int, Tuple[str, str, str, str]]] = []
        for k, info in self.history.items():
            counts.append((int(info.get("plays", 0)), tuple(k.split("||"))))

        counts.sort(reverse=True, key=lambda x: x[0])
        keys = [tuple(x[1]) for x in counts[:500]]
        songs = self._songs_from_keys(keys)

        self.current_category = None
        self._set_view_label("Suggestions (Most Played)")
        self._set_busy(True, "Rendering results…")
        self._populate_table_async(songs)
