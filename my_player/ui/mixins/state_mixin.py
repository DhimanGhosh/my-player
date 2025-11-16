import json
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt

from my_player.helpers.constants import STATE_DB, SPECIAL_FAV_CATEGORY, SPECIAL_PL_CATEGORY_PREFIX
from my_player.models.song import Song, key_to_dict, dict_to_key
from my_player.helpers.player_history_utils import save_history, save_custom


class StateMixin:
    """
    Handles persistence: _load_state(), _save_state(),
    view identity helpers, and base list helpers.

    NOTE:
    - Expects the concrete class (MyPlayerMain) to define:
        - self.vol_slider
        - self._on_volume_changed()
        - self.table
        - self.library
        - self.favourites
        - self.playlists
        - self.current_category
        - self._songs_from_keys()
    """

    def _load_state(self):
        """
        Load persistent state (volume, favourites, playlists, last view, sorting).
        """
        vol = 70
        fav_list = []
        playlists = {}
        last_cat = None
        self.last_song_key: Optional[Tuple[str, str, str, str]] = None

        try:
            if STATE_DB.exists():
                st = json.loads(STATE_DB.read_text(encoding="utf-8"))

                vol = int(st.get("volume", 70))
                last_cat = st.get("last_category")
                fav_list = st.get("favourites", [])
                playlists = st.get("playlists", {})

                ls = st.get("last_song")
                if isinstance(ls, dict):
                    self.last_song_key = dict_to_key(ls)

                self.sort_col = st.get("sort_col", None)
                self.sort_asc = bool(st.get("sort_asc", True))

        except Exception:
            # ignore broken state file
            pass

        # apply UI state (vol_slider + volume handler live on MyPlayerMain)
        self.vol_slider.setValue(max(0, min(100, vol)))
        self._on_volume_changed(self.vol_slider.value())

        # favourites
        try:
            self.favourites = set(
                dict_to_key(x) for x in fav_list if isinstance(x, dict)
            )
        except Exception:
            self.favourites = set()

        # playlists
        try:
            self.playlists = {
                name: [dict_to_key(x) for x in items if isinstance(x, dict)]
                for name, items in playlists.items()
            }
        except Exception:
            self.playlists = {}

        # restore last category ONLY if it still exists / is valid
        if (
            last_cat in self.library
            or last_cat in (SPECIAL_FAV_CATEGORY, None)
            or (
                isinstance(last_cat, str)
                and last_cat.startswith(SPECIAL_PL_CATEGORY_PREFIX)
            )
        ):
            self.current_category = last_cat

        # reflect sort indicator
        if self.sort_col is not None:
            self.table.horizontalHeader().setSortIndicator(
                self.sort_col,
                Qt.SortOrder.AscendingOrder
                if self.sort_asc
                else Qt.SortOrder.DescendingOrder,
            )

    def _save_state(self):
        """
        Save current persistent state to STATE_DB.
        """
        vol = int(self.vol_slider.value())
        data = {
            "volume": vol,
            "last_category": self.current_category,
            "favourites": [key_to_dict(k) for k in sorted(self.favourites)],
            "playlists": {
                name: [key_to_dict(k) for k in lst]
                for name, lst in self.playlists.items()
            },
            "last_song": (
                key_to_dict(self.current_song_key)
                if self.current_song_key
                else None
            ),
            "sort_col": self.sort_col,
            "sort_asc": self.sort_asc,
        }

        STATE_DB.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        save_history(self.history)
        save_custom(self.custom_urls)

    def _view_identity(self) -> Tuple[str, str]:
        """
        Determine what the current view represents:
        - ("favourites", "")
        - ("playlist", playlist_name)
        - ("category", category_name)
        """
        if self.current_category == SPECIAL_FAV_CATEGORY:
            return "favourites", ""
        if (
            self.current_category
            and self.current_category.startswith(SPECIAL_PL_CATEGORY_PREFIX)
        ):
            return (
                "playlist",
                self.current_category[len(SPECIAL_PL_CATEGORY_PREFIX) :],
            )
        if self.current_category:
            return "category", self.current_category
        return "category", ""

    def _base_list_for_current_view(self) -> List[Song]:
        """
        Return base song list depending on current view.
        """
        kind, name = self._view_identity()

        if kind == "favourites":
            return self._songs_from_keys(list(self.favourites))

        if kind == "playlist":
            return self._songs_from_keys(self.playlists.get(name, []))

        return self.library.get(self.current_category, [])
