from __future__ import annotations

from textwrap import dedent

class MaterialTheme:
    # Core palette
    HOVER      = "#32445A"   # hover/selected bg (used by delegate)
    SELECTION  = "#3C82F6"   # active selection color
    BORDER     = "#2A313A"
    TEXT       = "#E6E6E6"   # primary text

    # Row highlight colors
    HILITE_ROW = "#2E7D32"   # now-playing row bg
    HILITE_BAR = "#66BB6A"   # thin left bar on the row
    HILITE_TEXT = "#FFFFFF"  # text color on highlighted row

    BG_MAIN    = "#111418"   # main window background
    BG_INPUT   = "#1A1F26"   # inputs background
    BG_MENU    = "#141920"
    BG_HEADER  = "#1C232B"
    BG_PROGRESS= "#0F1318"

    DISABLED_TEXT = "#9AA3AD"
    BTN_BG        = "#243042"
    BTN_BORDER    = "#2F3B4D"
    BTN_HOVER     = "#2C3A4E"

    @staticmethod
    def stylesheet() -> str:
        c = MaterialTheme  # alias for brevity
        return dedent(f"""
            /* ========= Base ========= */
            * {{
                color: {c.TEXT};
            }}
            QWidget {{
                background: {c.BG_MAIN};
            }}
            QLabel[disabled="true"], QLabel:disabled {{
                color: {c.DISABLED_TEXT};
            }}
            QLabel {{
                color: {c.TEXT};
            }}

            /* ========= Inputs ========= */
            QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {{
                background: {c.BG_INPUT};
                border: 1px solid {c.BORDER};
                border-radius: 8px;
                padding: 6px;
                color: {c.TEXT};
            }}

            /* ========= Check / Radio ========= */
            QCheckBox, QRadioButton {{
                color: {c.TEXT};
            }}

            /* ========= Buttons ========= */
            QPushButton {{
                background: {c.BTN_BG};
                border: 1px solid {c.BTN_BORDER};
                border-radius: 10px;
                padding: 6px 12px;
            }}
            QPushButton:hover {{
                background: {c.BTN_HOVER};
            }}
            QPushButton:disabled {{
                color: {c.DISABLED_TEXT};
                border-color: {c.BORDER};
            }}

            /* ========= Menus / MessageBox ========= */
            QMenu {{
                background: {c.BG_MENU};
                color: {c.TEXT};
                border: 1px solid {c.BORDER};
            }}
            QMenu::item:selected {{
                background: {c.HOVER};
            }}
            QMessageBox QLabel {{
                color: {c.TEXT};
            }}

            /* ========= Tables ========= */
            QTableWidget {{
                gridline-color: {c.BORDER};
                background: {c.BG_MAIN};
                color: {c.TEXT};
                selection-background-color: {c.HOVER};
                selection-color: {c.TEXT};
            }}
            QHeaderView::section {{
                background: {c.BG_HEADER};
                color: {c.TEXT};
                border: 0px;
                padding: 6px;
                border-right: 1px solid {c.BORDER};
            }}

            /* ========= Progress ========= */
            QProgressBar {{
                background: {c.BG_PROGRESS};
                border: 1px solid {c.BORDER};
                border-radius: 6px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {c.SELECTION};
            }}
        """)
