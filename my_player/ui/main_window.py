from typing import Dict, List, Optional, Tuple
from collections import deque

# QT
from PyQt6.QtCore import (
    Qt, QTimer, QThreadPool, QEvent
)
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QLineEdit, QTableWidget,
    QHeaderView, QSplitter, QComboBox, QAbstractItemView, QSlider
)
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

# helpers -- constants
from my_player.helpers.constants import APP_NAME, APP_WINDOW_WIDTH, APP_WINDOW_HEIGHT

# helpers -- utilities
from my_player.helpers.db_utils import load_dur_db, save_dur_db
from my_player.helpers.player_history_utils import load_history, load_custom

# io
from my_player.io.library_io import load_library_from_csvs

# models
from my_player.models.song import Song

# services
from my_player.services.download import DownloadManager

# UI -- theme
from my_player.ui.theme import MaterialTheme

# UI -- widgets
from my_player.ui.widgets.busy_overlay import BusyOverlay
from my_player.ui.widgets.empty_hint import EmptyHint
from my_player.ui.widgets.current_song_highlighter import MaterialRowDelegate
from my_player.ui.widgets.seek_bar import SeekSlider
from my_player.ui.widgets.song_time import SongTimeLabelMMSS

# UI -- mixins
from my_player.ui.mixins.state_mixin import StateMixin
from my_player.ui.mixins.category_playlist_mixin import CategoryPlaylistMixin
from my_player.ui.mixins.search_table_mixin import SearchTableMixin
from my_player.ui.mixins.favourites_playlists_mixin import FavouritesPlaylistsMixin
from my_player.ui.mixins.player_queue_mixin import PlayerQueueMixin
from my_player.ui.mixins.download_fileops_mixin import DownloadFileOpsMixin
from my_player.ui.mixins.suggestions_mixin import SuggestionsMixin
from my_player.ui.mixins.inline_edit_mixin import InlineEditMixin
from my_player.ui.mixins.busy_mixin import BusyMixin
from my_player.ui.mixins.context_menu_mixin import ContextMenuMixin
from my_player.ui.mixins.background_scan_mixin import BackgroundScanMixin


class MyPlayerMain(
    QMainWindow,
    StateMixin,
    CategoryPlaylistMixin,
    SearchTableMixin,
    FavouritesPlaylistsMixin,
    PlayerQueueMixin,
    DownloadFileOpsMixin,
    SuggestionsMixin,
    InlineEditMixin,
    BusyMixin,
    ContextMenuMixin,
    BackgroundScanMixin
):
    COL_FAV = 0
    COL_CATEGORY = 1
    COL_TITLE = 2
    COL_ALBUM = 3
    COL_ARTISTS = 4
    COL_DURATION = 5

    def __init__(self):
        super().__init__()

        self._setup_app_window()

        # --- Data/state in memory -------------------------------------------------
        self.library: Dict[str, List[Song]] = load_library_from_csvs()
        self.current_category: Optional[str] = None
        self.current_list: List[Song] = []
        self._user_seeking: bool = False
        self._duration_ms: int = 0

        # Duration cache (mixed legacy sec/ms -> normalize below)
        self.duration_db: Dict[str, int] = load_dur_db()

        # Normalize duration DB (convert ms→s, drop bad values) and persist once.
        changed = False
        for k, v in list(self.duration_db.items()):
            sec = self._sec_from_cache_val(v)
            if sec is None:
                self.duration_db.pop(k, None)
                changed = True
            elif sec != v:
                self.duration_db[k] = sec
                changed = True
        if changed:
            save_dur_db(self.duration_db)

        self.history: Dict[str, dict] = load_history()
        self.custom_urls: Dict[str, str] = load_custom()

        self.favourites: set[Tuple[str, str, str, str]] = set()
        self.playlists: Dict[str, List[Tuple[str, str, str, str]]] = {}

        # Typing debounce for search
        self._type_debounce = QTimer(self)
        self._type_debounce.setInterval(220)
        self._type_debounce.setSingleShot(True)
        self._type_debounce.timeout.connect(self._apply_search_now)

        # Incremental table-population state
        self._populate_timer: Optional[QTimer] = None
        self._populate_source: List[Song] = []
        self._populate_index: int = 0
        self._populate_gen: int = 0

        # --- Download manager: fully off GUI thread --------------------------------
        self.dlm = DownloadManager(self, bg_concurrency=6, custom_map=self.custom_urls, history=self.history)
        self.dlm.file_ready.connect(self._on_file_ready)
        self.dlm.progress.connect(self._dl_progress)
        self.dlm.queue_paused.connect(self._on_queue_paused)

        self._pending_autoplay_key: Optional[Tuple[str, str, str, str]] = None
        self._prefetch_triggered: bool = False
        self._prefetch_in_progress: bool = False
        self._prefetch_next_key: Optional[Tuple[str, str, str, str]] = None
        self._deferred_hi: deque[Tuple[Song, bool]] = deque()

        # --- Player ----------------------------------------------------------------
        self.audio_output = QAudioOutput()
        self.player = QMediaPlayer()
        self.player.setAudioOutput(self.audio_output)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.positionChanged.connect(self._on_pos_changed)
        self.player.durationChanged.connect(self._on_duration_changed)

        # Global sort state (persisted)
        self.sort_col: Optional[int] = None
        self.sort_asc: bool = True

        # Playback queue/context
        self.play_queue: List[Song] = []
        self.play_index: int = -1
        self.play_context: Optional[Tuple[str, str]] = None
        self.current_song_key: Optional[Tuple[str, str, str, str]] = None

        # --- Search infra / overlays ----------------------------------------------
        self.search_pool = QThreadPool.globalInstance()
        self._search_seq = 0
        self._last_search_seq = 0
        self._search_running = False
        self.busy = BusyOverlay(self, "Searching…")
        self.empty_hint = EmptyHint(self, "No result found")

        # "no results" overlay on the table viewport
        self.no_results_hint = QLabel("No results found")
        self.no_results_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_results_hint.setStyleSheet("color:#98a2b3; font-size:14px;")
        self.no_results_hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.no_results_hint.hide()

        # --- Build UI and restore persisted state ----------------------------------
        self._build_ui()
        self._load_state()
        self._refresh_categories()
        self._refresh_playlists_panel()
        self._rebuild_playlists_menu()
        self._rebuild_suggestions_menu()
        self._sync_view_label_from_state()

        # Render first view immediately; DO NOT start any background downloads here.
        self._apply_search_now()

    def _setup_app_window(self) -> None:
        self.setWindowTitle(APP_NAME)
        self.resize(APP_WINDOW_WIDTH, APP_WINDOW_HEIGHT)
        self.setStyleSheet(MaterialTheme.stylesheet())

    # ---------- UI ----------
    def _build_ui(self):
        """Builds the full UI with responsive table + visible sort arrows by default."""
        central = QWidget()
        self.setCentralWidget(central)

        # ---------- Left column: Categories + Playlists ----------
        self.category_list = QListWidget()
        self.category_list.itemSelectionChanged.connect(self._on_cat_selected)
        self.category_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.category_list.customContextMenuRequested.connect(self._category_context_menu)

        self.playlist_list = QListWidget()
        self.playlist_list.itemSelectionChanged.connect(self._on_pl_selected)
        self.playlist_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.playlist_list.customContextMenuRequested.connect(self._playlist_context_menu)

        left = QVBoxLayout()
        lab1 = QLabel("Categories"); lab1.setStyleSheet("font-weight:600;")
        lab2 = QLabel("Playlists");  lab2.setStyleSheet("font-weight:600; margin-top:8px;")
        left.addWidget(lab1); left.addWidget(self.category_list, 1)
        left.addWidget(lab2); left.addWidget(self.playlist_list, 1)
        left_box = QWidget(); left_box.setLayout(left)

        # ---------- Right column: Search + Table + Controls ----------
        self.view_label = QLabel("Category: (none)")
        self.view_label.setStyleSheet("font-weight:700; font-size:16px;")

        # Search row
        scope_line = QHBoxLayout()
        self.scope_combo = QComboBox(); self.scope_combo.addItems(["Category", "Global"])
        scope_line.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search title / album / artist…")
        self.search_edit.setClearButtonEnabled(True)
        scope_line.addWidget(self.search_edit, 1)
        scope_line.addWidget(QLabel("Scope:"))
        scope_line.addWidget(self.scope_combo)

        # Debounced search
        self.search_edit.textChanged.connect(lambda _: self._type_debounce.start())
        self.scope_combo.currentIndexChanged.connect(lambda _: self._apply_search_now())

        # Results table
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["★", "Category", "Song", "Film/Album", "Artists", "Duration"])
        self.table.setShowGrid(False)

        hh = self.table.horizontalHeader()
        hh.setSortIndicatorShown(True)
        hh.setSectionsClickable(True)
        hh.sectionClicked.connect(self._on_header_clicked)

        hh.setSectionResizeMode(self.COL_FAV,      QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_CATEGORY, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_TITLE,    QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(self.COL_ALBUM,    QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(self.COL_ARTISTS,  QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(self.COL_DURATION, QHeaderView.ResizeMode.ResizeToContents)

        self.table.setColumnWidth(self.COL_FAV, 36)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._play_selected)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._table_context_menu)

        # We sort the *data* then (re)render in batches; avoid built-in row-sorting here.
        self.table.setSortingEnabled(False)
        self.table.setMouseTracking(True)
        self.table.setAutoScroll(False)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)

        # Row painter / style
        self.row_delegate = MaterialRowDelegate(self)
        self.table.setItemDelegate(self.row_delegate)
        self.table.setAlternatingRowColors(False)
        self.table.setStyleSheet(self.table.styleSheet() + " QTableWidget::item { padding: 6px; } ")

        # Empty / no-results overlay tied to the table viewport
        self.no_results_hint.setParent(self.table.viewport())
        self.no_results_hint.resize(self.table.viewport().size())
        self.table.viewport().installEventFilter(self)

        # Make sure sort arrows are visible even on first launch
        if self.sort_col is None:
            self.sort_col = self.COL_TITLE
            self.sort_asc = True
        hh.setSortIndicator(
            self.sort_col,
            Qt.SortOrder.AscendingOrder if self.sort_asc else Qt.SortOrder.DescendingOrder
        )

        # Playback seek + clock
        self.seek = SeekSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderPressed.connect(self._on_seek_start)
        self.seek.sliderReleased.connect(self._on_seek_commit)
        self.seek.sliderMoved.connect(self._on_seek_preview)
        self.time_label = SongTimeLabelMMSS()

        seek_line = QHBoxLayout()
        seek_line.addWidget(self.seek, 1)
        seek_line.addWidget(self.time_label)
        seek_box = QWidget(); seek_box.setLayout(seek_line)
        seek_box.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        seek_box.customContextMenuRequested.connect(self._player_context_menu)

        # Controls row
        self.playpause_btn = QPushButton(); self._set_play_icon(False)
        self.prev_btn = QPushButton("⏮ Prev")
        self.next_btn = QPushButton("⏭ Next")
        self.download_btn = QPushButton("⬇ Download Library Now")
        self.add_cat_btn = QPushButton("➕ Add/Append Category")
        self.remove_pl_sel_btn = QPushButton("- Remove Selected from Playlist")
        self.remove_pl_sel_btn.setVisible(False)

        self.download_btn.clicked.connect(self._kick_background_missing_scan)
        self.add_cat_btn.clicked.connect(self._add_category)
        self.playpause_btn.clicked.connect(self._toggle_playpause)
        self.prev_btn.clicked.connect(self._prev_song)
        self.next_btn.clicked.connect(self._next_song)
        self.remove_pl_sel_btn.clicked.connect(self._remove_selected_from_current_playlist)

        self.vol_label = QLabel("Vol:")
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(70)
        self.vol_slider.setFixedWidth(120)
        self.vol_slider.valueChanged.connect(self._on_volume_changed)

        ctrl_line = QHBoxLayout()
        for w in (self.playpause_btn, self.prev_btn, self.next_btn,
                self.download_btn, self.add_cat_btn, self.remove_pl_sel_btn,
                self.vol_label, self.vol_slider):
            ctrl_line.addWidget(w)
        ctrl_line.addStretch(1)
        ctrl_box = QWidget(); ctrl_box.setLayout(ctrl_line)

        # Assemble right column
        right = QVBoxLayout()
        right.addWidget(self.view_label)
        scope_box = QWidget(); scope_box.setLayout(scope_line)
        right.addWidget(scope_box)
        right.addWidget(self.table)
        right.addWidget(seek_box)
        right.addWidget(ctrl_box)
        right_box = QWidget(); right_box.setLayout(right)

        # Splitter layout
        split = QSplitter()
        split.addWidget(left_box)
        split.addWidget(right_box)
        split.setSizes([300, 1000])

        # Attach to central widget
        lay = QVBoxLayout(central)
        lay.addWidget(split)

        # Status bar
        self.status = self.statusBar()
        self.cur_info = QLabel("Ready.")
        self.cur_info.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cur_info.customContextMenuRequested.connect(self._player_context_menu)
        self.dl_status = QLabel("")
        self.status.addPermanentWidget(self.cur_info)
        self.status.addPermanentWidget(self.dl_status)

        # Menus
        menubar = self.menuBar()
        m_file = menubar.addMenu("&File")
        m_file.setStyleSheet(MaterialTheme.stylesheet())
        m_file.addAction(QAction("Reload CSVs", self, triggered=self._reload_csvs))
        m_file.addAction(QAction("Exit", self, triggered=self.close))

        self.m_playlists = menubar.addMenu("&Playlists")
        self.m_playlists.setStyleSheet(MaterialTheme.stylesheet())
        self.act_show_fav = QAction("Favourites", self, triggered=self._show_favourites)
        self.m_playlists.addAction(self.act_show_fav)
        self.m_playlists.addSeparator()

        self.m_suggest = menubar.addMenu("&Suggestions")
        self.m_suggest.setStyleSheet(MaterialTheme.stylesheet())
        self.m_suggest.addAction(QAction("Show Top Suggestions", self, triggered=self._show_suggestions))

        # Busy overlay tied to the window
        self.empty_hint.setParent(self.table.viewport())
        self.empty_hint.resize(self.table.viewport().size())
        self.table.viewport().installEventFilter(self)

    # ---------- Event filter for overlays ----------
    def eventFilter(self, obj, event):
        if obj is self.table.viewport():
            if event.type() in (
                QEvent.Type.Resize,
                QEvent.Type.Show,
                QEvent.Type.LayoutRequest
            ):
                self.no_results_hint.resize(self.table.viewport().size())
        return super().eventFilter(obj, event)

    # ---------- Busy overlay ----------
    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.busy: self.busy.setGeometry(self.rect())
