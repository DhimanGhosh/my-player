from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QFont, QPen
from PyQt6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle

from my_player.ui.theme import MaterialTheme
from my_player.models.song import Song


class MaterialRowDelegate(QStyledItemDelegate):
    def __init__(self, parent):
        super().__init__(parent.table)
        self.main = parent
        self.font_title_bold = QFont()
        self.font_title_bold.setBold(True)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index):
        """
        Custom paint that:
        - fully covers the cell (bleeds 1px left/right) so gridlines or padding don't peek through
        - highlights the now-playing row
        - keeps default painting for non-title columns
        """
        row = index.row()
        is_now = False
        if 0 <= row < len(self.main.current_list) and self.main.current_song_key is not None:
            s: "Song" = self.main.current_list[row]
            is_now = (s.key() == self.main.current_song_key)

        painter.save()
        # Expand the rect by 1px on both sides so no grid/padding shows as a vertical stripe
        rect = option.rect.adjusted(-1, 0, +1, 0)

        # Backgrounds
        if is_now:
            painter.fillRect(rect, QColor(MaterialTheme.HILITE_ROW))
            # left accent bar
            bar_rect = QRect(rect.left(), rect.top(), 4, rect.height())
            painter.fillRect(bar_rect, QColor(MaterialTheme.HILITE_BAR))
        else:
            if option.state & QStyle.StateFlag.State_Selected:
                painter.fillRect(rect, QColor(MaterialTheme.HOVER))
            elif option.state & QStyle.StateFlag.State_MouseOver:
                painter.fillRect(rect, QColor(MaterialTheme.HOVER))

        # Title column gets custom bold text when now-playing
        if is_now and index.column() == self.main.COL_TITLE:
            opt = QStyleOptionViewItem(option)
            opt.text = ""
            self.main.table.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter)
            painter.setPen(QPen(QColor(MaterialTheme.HILITE_TEXT)))
            metrics = painter.fontMetrics()
            r = option.rect.adjusted(6, 0, -6, 0)
            text = index.data() or ""
            elided = metrics.elidedText(text, Qt.TextElideMode.ElideRight, r.width())
            painter.setFont(self.font_title_bold)
            painter.drawText(r, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)
        else:
            super().paint(painter, option, index)

        painter.restore()
