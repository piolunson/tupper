"""Custom widgets: frameless shell, technical section headers, pixel editor."""

from __future__ import annotations

import random

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPen,
    QTextOption,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..core.tupper import HEIGHT, WIDTH, Bitmap, empty_bitmap
from .theme import Palette, spaced_font

ROOT_MARGIN = 6


# --------------------------------------------------------------------------
# small helpers
# --------------------------------------------------------------------------

def label(text: str, object_name: str = "", family: str | None = None) -> QLabel:
    widget = QLabel(text)
    if object_name:
        widget.setObjectName(object_name)
    if family:
        widget.setFont(QFont(family))
    return widget


def dim_label(text: str, family: str) -> QLabel:
    widget = label(text, "Dim", family)
    widget.setWordWrap(False)
    return widget


def button(text: str, family: str, kind: str = "", tooltip: str = "") -> QPushButton:
    widget = QPushButton(text)
    if kind:
        widget.setObjectName(kind)
    widget.setFont(spaced_font(family, 9, QFont.Weight.Bold, 0.5))
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    widget.setAutoDefault(False)
    widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    if tooltip:
        widget.setToolTip(tooltip)
    return widget


def hline(palette: Palette) -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFixedHeight(2)
    line.setStyleSheet(f"background: {palette.line}; border: none;")
    return line


class SectionHeader(QWidget):
    """`[ 01 ] TITLE ------------------------- HINT`"""

    def __init__(self, number: str, title: str, hint: str, family: str, palette: Palette):
        super().__init__()
        self._family = family
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        index = label(f"[ {number} ]", "Section", family)
        index.setFont(spaced_font(family, 9, QFont.Weight.Bold, 1.5))
        name = label(title, "SectionTitle", family)
        name.setFont(spaced_font(family, 10, QFont.Weight.Bold, 2.5))
        hint_label = label(hint, "Dim", family)
        hint_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        hint_label.setFont(spaced_font(family, 8, QFont.Weight.Normal, 1.0))
        row.addWidget(index)
        row.addWidget(name)
        row.addStretch(1)
        row.addWidget(hint_label)
        self.setFixedHeight(24)


# --------------------------------------------------------------------------
# frameless window
# --------------------------------------------------------------------------

_EDGE = 7


def _edges_at(pos: QPoint, size: QSize) -> Qt.Edges:
    edges = Qt.Edge(0)
    if pos.x() <= _EDGE:
        edges |= Qt.Edge.LeftEdge
    if pos.x() >= size.width() - _EDGE:
        edges |= Qt.Edge.RightEdge
    if pos.y() <= _EDGE:
        edges |= Qt.Edge.TopEdge
    if pos.y() >= size.height() - _EDGE:
        edges |= Qt.Edge.BottomEdge
    return edges


def _cursor_for(edges: Qt.Edges):
    left = bool(edges & Qt.Edge.LeftEdge)
    right = bool(edges & Qt.Edge.RightEdge)
    top = bool(edges & Qt.Edge.TopEdge)
    bottom = bool(edges & Qt.Edge.BottomEdge)
    if (left and top) or (right and bottom):
        return Qt.CursorShape.SizeFDiagCursor
    if (right and top) or (left and bottom):
        return Qt.CursorShape.SizeBDiagCursor
    if left or right:
        return Qt.CursorShape.SizeHorCursor
    if top or bottom:
        return Qt.CursorShape.SizeVerCursor
    return Qt.CursorShape.ArrowCursor


class FramelessWindow(QWidget):
    """Frameless shell with native edge resizing and a custom title bar slot."""

    def __init__(self, family: str):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setMouseTracking(True)
        self.setMinimumSize(1180, 700)
        self._family = family

    def mouseMoveEvent(self, event: QMouseEvent):
        self.setCursor(_cursor_for(_edges_at(event.position().toPoint(), self.size())))
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            edges = _edges_at(event.position().toPoint(), self.size())
            handle = self.windowHandle()
            if edges and handle is not None and handle.startSystemResize(edges):
                event.accept()
                return
        super().mousePressEvent(event)


class TitleBar(QFrame):
    def __init__(self, window: QWidget, family: str, palette: Palette, title: str, subtitle: str):
        super().__init__()
        self.setObjectName("TitleBar")
        self._window = window
        self._palette = palette
        self._drag_origin: QPoint | None = None
        self.setFixedHeight(52)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 0, 6, 0)
        row.setSpacing(10)

        mark = label("T", "BrandMark", family)
        mark.setFont(spaced_font(family, 15, QFont.Weight.Bold, 0))
        mark.setFixedSize(26, 26)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)

        brand = label(title, "Brand", family)
        brand.setFont(spaced_font(family, 15, QFont.Weight.Bold, 4.5))

        sub = label(subtitle, "Dim", family)
        sub.setFont(spaced_font(family, 8, QFont.Weight.Normal, 1.0))
        sub.setAlignment(Qt.AlignmentFlag.AlignBottom)

        row.addWidget(mark)
        row.addWidget(brand)
        row.addWidget(sub)
        row.addStretch(1)

        self.invert_btn = button("[ INVERT ]", family, tooltip="Toggle white / dark sheet (Ctrl+I)")
        self.invert_btn.setCheckable(True)
        row.addWidget(self.invert_btn)

        self.min_btn = button("_", family, "WindowBtn", "Minimise")
        self.max_btn = button("[]", family, "WindowBtn", "Maximise")
        self.close_btn = button("X", family, "WindowBtn", "Close")
        self.close_btn.setObjectName("WindowBtn")
        self.close_btn.setProperty("danger", True)
        for btn in (self.min_btn, self.max_btn, self.close_btn):
            btn.setFixedSize(30, 26)
            btn.setFont(spaced_font(family, 11, QFont.Weight.Bold, 0))
            row.addWidget(btn)

        self.min_btn.clicked.connect(self._window.showMinimized)
        self.max_btn.clicked.connect(self.toggle_max)
        self.close_btn.clicked.connect(self._window.close)

    def toggle_max(self):
        if self._window.isMaximized():
            self._window.showNormal()
        else:
            self._window.showMaximized()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self._window.windowHandle()
            if handle is not None and handle.startSystemMove():
                event.accept()
                return
            self._drag_origin = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_origin is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self._window.move(event.globalPosition().toPoint() - self._drag_origin)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_origin = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_max()
        super().mouseDoubleClickEvent(event)


# --------------------------------------------------------------------------
# pixel editor
# --------------------------------------------------------------------------

class PixelCanvas(QWidget):
    """106x17 editor plate. Left click draws, right click erases, drag paints."""

    edited = Signal()
    hovered = Signal(int, int)  # row, col; -1 when outside

    def __init__(self, family: str, palette: Palette, editable: bool = True):
        super().__init__()
        self._family = family
        self._palette = palette
        self._bitmap: Bitmap = empty_bitmap()
        self._editable = editable
        self._cell = 4.0
        self._origin = QPoint(0, 0)
        self._paint_value: int | None = None
        self._hover = (-1, -1)
        self._placeholder = ""
        self.setMouseTracking(True)
        self.setMinimumHeight(80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # geometry -------------------------------------------------------------
    def _layout_plate(self):
        avail_w = self.width() - 8
        avail_h = self.height() - 8
        if avail_w <= 0 or avail_h <= 0:
            return QRect(0, 0, 0, 0)
        cell = min(avail_w / WIDTH, avail_h / HEIGHT)
        self._cell = cell
        plate_w = int(cell * WIDTH)
        plate_h = int(cell * HEIGHT)
        x = (self.width() - plate_w) // 2
        y = (self.height() - plate_h) // 2
        self._origin = QPoint(x, y)
        return QRect(x, y, plate_w, plate_h)

    def heightForWidth(self, width: int) -> int:
        cell = max(1.0, (width - 8) / WIDTH)
        return int(cell * HEIGHT) + 10

    def hasHeightForWidth(self) -> bool:
        return True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        wanted = self.heightForWidth(self.width())
        if wanted != self.height() and self.isVisible():
            self.setFixedHeight(wanted)

    def _cell_at(self, pos: QPoint) -> tuple[int, int]:
        if self._cell <= 0:
            return -1, -1
        col = int((pos.x() - self._origin.x()) / self._cell)
        row = int((pos.y() - self._origin.y()) / self._cell)
        if 0 <= col < WIDTH and 0 <= row < HEIGHT:
            return row, col
        return -1, -1

    # state ---------------------------------------------------------------
    def set_bitmap(self, bitmap: Bitmap, notify: bool = False):
        self._bitmap = [list(row) for row in bitmap]
        if notify:
            self.edited.emit()
        self.update()

    def bitmap(self) -> Bitmap:
        return [list(row) for row in self._bitmap]

    def set_editable(self, editable: bool):
        self._editable = editable
        self.setCursor(Qt.CursorShape.CrossCursor if editable else Qt.CursorShape.ArrowCursor)

    def set_placeholder(self, text: str):
        self._placeholder = text
        self.update()

    def set_palette(self, palette: Palette):
        self._palette = palette
        self.update()

    # painting ------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(self.rect(), QColor(self._palette.bg))
        plate = self._layout_plate()
        if plate.width() <= 0:
            return

        painter.fillRect(plate, QColor("#FFFFFF"))
        cell = self._cell
        ink = QColor("#000000")
        for row in range(HEIGHT):
            for col in range(WIDTH):
                if self._bitmap[row][col]:
                    rect = QRectF(
                        plate.x() + col * cell,
                        plate.y() + row * cell,
                        cell + 0.02,
                        cell + 0.02,
                    )
                    painter.fillRect(rect, ink)

        # pixel grid, only when it stays legible
        if cell >= 5.0:
            painter.setPen(QPen(QColor(0, 0, 0, 60), 1))
            for col in range(1, WIDTH):
                x = plate.x() + col * cell
                painter.drawLine(int(x), plate.y(), int(x), plate.y() + plate.height())
            for row in range(1, HEIGHT):
                y = plate.y() + row * cell
                painter.drawLine(plate.x(), int(y), plate.x() + plate.width(), int(y))

        # plate border
        painter.setPen(QPen(QColor("#000000"), 2))
        painter.drawRect(plate.adjusted(0, 0, -1, -1))
        painter.setPen(QPen(QColor(self._palette.accent), 1))
        painter.drawRect(plate.adjusted(-3, -3, 2, 2))

        # hover cell
        if self._editable and self._hover[0] >= 0 and cell >= 3:
            row, col = self._hover
            painter.setPen(QPen(QColor(self._palette.accent), 2))
            painter.drawRect(
                QRectF(plate.x() + col * cell, plate.y() + row * cell, cell, cell)
            )

        # registration ticks (technical sheet corners)
        painter.setPen(QPen(QColor(self._palette.dim), 1))
        for dx, dy in ((-6, 0), (0, -6), (plate.width() + 2, 0), (0, plate.height() + 2)):
            painter.drawLine(
                plate.x() + dx, plate.y() + dy, plate.x() + dx + 4, plate.y() + dy
            )
            painter.drawLine(
                plate.x() + dx, plate.y() + dy, plate.x() + dx, plate.y() + dy + 4
            )

        if self._placeholder and not any(any(row) for row in self._bitmap):
            painter.setPen(QColor("#000000"))
            font = spaced_font(self._family, 8, QFont.Weight.Bold, 1.5)
            painter.setFont(font)
            painter.drawText(plate, Qt.AlignmentFlag.AlignCenter, self._placeholder)

        painter.end()

    # interaction ---------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent):
        if not self._editable:
            return
        row, col = self._cell_at(event.position().toPoint())
        if row < 0:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._paint_value = 1
        elif event.button() == Qt.MouseButton.RightButton:
            self._paint_value = 0
        else:
            return
        self._paint(row, col)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        row, col = self._cell_at(event.position().toPoint())
        if (row, col) != self._hover:
            self._hover = (row, col)
            self.hovered.emit(row, col)
            self.update()
        if self._editable and self._paint_value is not None and event.buttons():
            if row >= 0:
                self._paint(row, col)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._paint_value = None
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        if self._hover != (-1, -1):
            self._hover = (-1, -1)
            self.hovered.emit(-1, -1)
            self.update()
        super().leaveEvent(event)

    def _paint(self, row: int, col: int):
        value = self._paint_value
        if value is None:
            return
        if self._bitmap[row][col] != value:
            self._bitmap[row][col] = value
            self.edited.emit()
            self.update()


# --------------------------------------------------------------------------
# k field with typewriter reveal
# --------------------------------------------------------------------------

class KField(QPlainTextEdit):
    def __init__(self, family: str):
        super().__init__()
        self._family = family
        self._full = ""
        self._shown = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFixedHeight(110)
        self.setFont(QFont(family, 8))
        self.setCursorWidth(0)

    def full_text(self) -> str:
        return self._full

    def set_text(self, text: str, animate: bool = False):
        self._full = text
        self._timer.stop()
        if not animate or not text:
            self.setPlainText(text)
            self._shown = len(text)
            self.verticalScrollBar().setValue(0)
            return
        self._shown = 0
        self.setPlainText("")
        self._timer.start()

    def _tick(self):
        self._shown = min(len(self._full), self._shown + 21)
        chunk = self._full[: self._shown]
        if self._shown < len(self._full):
            rng = random.Random(self._shown)
            tail = "".join(str(rng.randrange(10)) for _ in range(14))
            self.setPlainText(chunk + tail)
            self.verticalScrollBar().setValue(0)
        else:
            self.setPlainText(self._full)
            self.verticalScrollBar().setValue(0)
            self._timer.stop()
