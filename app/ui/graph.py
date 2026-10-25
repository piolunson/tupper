"""The LOCATE view: the real formula plotted in the (x, y) plane.

The graph draws cells from the actual big-integer formula, tiled by background
workers and cached in world coordinates so panning reuses work.  The x extent
is the full 106-column bitmap (so the portrait never collapses to a sliver);
the y axis is the zoomable one, because that is where the other bitmaps live.
Both axes are reversed (x = 0 on the right, y = k at the top) -- the
orientation in which the formula's portrait reads upright.
"""

from __future__ import annotations

import math
import os

from PySide6.QtCore import QPointF, QRectF, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QImage,
    QMouseEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..core.tupper import (
    HEIGHT,
    ORIGINAL_K,
    WIDTH,
    cell_is_black,
    decode_n,
)
from ..workers.tiles import TileRequest, TileResult, TileSignals, TileTask
from .theme import Palette, spaced_font

TILE = 216
PLOT_LEFT = 88.0
PLOT_BOTTOM = 26.0
MIN_ZOOM = 0.02
MAX_ZOOM = 72.0
MAX_SX = 40.0
CANDIDATES = (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000, 10000)


def _sci(value: int) -> str:
    text = str(value)
    if len(text) <= 4:
        return text
    return f"{text[0]}.{text[1:3]}E+{len(text) - 1}"


def _log10_big(value: int) -> float:
    digits = len(str(value))
    if digits <= 15:
        return math.log10(value) if value > 0 else 0.0
    head = int(str(value)[:15])
    return math.log10(head) + (digits - 15)


def _nice_step(minimum: float) -> float:
    for candidate in CANDIDATES:
        if candidate >= minimum:
            return float(candidate)
    exponent = 10 ** int(math.floor(math.log10(minimum)))
    for factor in (5, 2, 1):
        if exponent * factor >= minimum:
            return float(exponent * factor)
    return float(exponent * 10)


def _offset_label(offset: int) -> str:
    if offset == 0:
        return "K"
    sign = "+" if offset > 0 else "-"
    magnitude = abs(offset)
    if magnitude < 1_000_000:
        return f"K{sign}{magnitude}"
    return f"K{sign}{_sci(magnitude)}"


class GraphView(QWidget):
    status = Signal(str)
    probe = Signal(str)

    def __init__(self, family: str, palette: Palette):
        super().__init__()
        self._family = family
        self._palette = palette
        self._k = ORIGINAL_K
        self._n_ref = self._k // 17
        self._zoom = 12.0
        self._cu = WIDTH / 2
        self._cv = HEIGHT / 2
        self._at_fit = True
        self._needs_fit = True

        self._epoch = 0
        self._tiles: dict[tuple[int, int], QImage] = {}
        self._pending: set[tuple[int, int]] = set()

        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(max(2, min(4, os.cpu_count() or 2)))
        self._signals = TileSignals()
        self._signals.finished.connect(self._on_tile)

        self._panning = False
        self._pan_anchor = QPointF()
        self._pan_center = (self._cu, self._cv)
        self._hover = QPointF(-1, -1)
        self._hover_text = ""

        self._flight: dict | None = None
        self._flight_timer = QTimer(self)
        self._flight_timer.setInterval(46)
        self._flight_timer.timeout.connect(self._flight_tick)
        self._flash = 0
        self._flash_timer = QTimer(self)
        self._flash_timer.setInterval(90)
        self._flash_timer.timeout.connect(self._flash_tick)

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(460, 220)
        self.setCursor(Qt.CursorShape.CrossCursor)

    # ------------------------------------------------------------------ scales
    def _plot_size(self) -> tuple[float, float]:
        return (
            max(1.0, self.width() - PLOT_LEFT),
            max(1.0, self.height() - PLOT_BOTTOM),
        )

    def _fit_sx(self) -> float:
        plot_w, _ = self._plot_size()
        return max(3.0, (plot_w - 24) / WIDTH)

    def _sx(self) -> float:
        return max(self._fit_sx(), min(MAX_SX, self._zoom))

    def _sy(self) -> float:
        return max(MIN_ZOOM, min(MAX_ZOOM, self._zoom))

    def world_to_screen(self, u: float, v: float) -> QPointF:
        plot_w, plot_h = self._plot_size()
        return QPointF(
            PLOT_LEFT + plot_w / 2 + (u - self._cu) * self._sx(),
            plot_h / 2 + (v - self._cv) * self._sy(),
        )

    def screen_to_world(self, pos: QPointF) -> tuple[float, float]:
        plot_w, plot_h = self._plot_size()
        return (
            self._cu + (pos.x() - PLOT_LEFT - plot_w / 2) / self._sx(),
            self._cv + (pos.y() - plot_h / 2) / self._sy(),
        )

    def _plot_rect(self) -> QRectF:
        plot_w, plot_h = self._plot_size()
        return QRectF(PLOT_LEFT, 0, plot_w, plot_h)

    # ------------------------------------------------------------------ state
    def set_k(self, k: int, reset: bool = True):
        self._k = max(0, k)
        self._n_ref = self._k // 17
        if reset:
            self.reset_view()
        else:
            self._invalidate()
            self.update()

    def set_palette(self, palette: Palette):
        self._palette = palette
        self._invalidate()
        self.update()

    def reset_view(self):
        if self._flight is not None:
            self._flight_timer.stop()
            self._flight = None
            self._flash = 0
            self._flash_timer.stop()
        self._zoom = min(MAX_ZOOM, self._fit_sx())
        self._cu = WIDTH / 2
        self._cv = HEIGHT / 2
        self._at_fit = True
        self._invalidate()
        self.update()
        self.status.emit(
            f"[ VIEW ] BAND X 0..105 / Y K..K+16   {self._sy():0.2f} PX PER ROW"
        )

    def zoom_step(self, factor: float):
        plot_w, plot_h = self._plot_size()
        self.zoom_at(QPointF(PLOT_LEFT + plot_w / 2, plot_h / 2), factor)

    def zoom_at(self, pos: QPointF, factor: float):
        new_zoom = max(MIN_ZOOM, min(MAX_ZOOM, self._zoom * factor))
        if abs(new_zoom - self._zoom) < 1e-9:
            return
        before_u, before_v = self.screen_to_world(pos)
        old_sx = self._sx()
        plot_w, plot_h = self._plot_size()
        self._zoom = new_zoom
        self._at_fit = False
        new_sx = self._sx()
        if abs(new_sx - old_sx) > 1e-9:
            self._cu = before_u - (pos.x() - PLOT_LEFT - plot_w / 2) / new_sx
            self._cu = max(0.0, min(float(WIDTH), self._cu))
        self._cv = before_v - (pos.y() - plot_h / 2) / self._sy()
        self._cv = max(-1e9, min(1e9, self._cv))
        self._invalidate()
        self.update()
        self.status.emit(
            f"[ ZOOM ] {self._sx():0.2f} PX/CELL X // {self._sy():0.2f} PX/ROW Y"
        )

    def _invalidate(self):
        self._epoch += 1
        self._tiles.clear()
        self._pending.clear()

    # ------------------------------------------------------------------ tiles
    def _tile_geometry(self):
        sx, sy = self._sx(), self._sy()
        plot_w, plot_h = self._plot_size()
        u0 = self._cu - plot_w / 2 / sx
        v0 = self._cv - plot_h / 2 / sy
        tw = TILE / sx
        th = TILE / sy
        return sx, sy, u0, v0, tw, th

    def _ensure_tiles(self):
        sx, sy, u0, v0, tw, th = self._tile_geometry()
        plot_w, plot_h = self._plot_size()
        i0 = math.floor(u0 / tw)
        i1 = math.floor((u0 + plot_w / sx) / tw)
        j0 = math.floor(v0 / th)
        j1 = math.floor((v0 + plot_h / sy) / th)
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                key = (i, j)
                if key in self._tiles or key in self._pending:
                    continue
                if len(self._pending) >= 24:
                    return
                self._pending.add(key)
                request = TileRequest(
                    key=key,
                    epoch=self._epoch,
                    k=self._k,
                    u0=i * tw,
                    v0=j * th,
                    scale=sx,
                    scale_y=sy,
                    size=TILE,
                )
                self._pool.start(TileTask(request, self._signals))

    def _on_tile(self, result: TileResult):
        if result.epoch != self._epoch:
            self._pending.discard(result.key)
            return
        self._pending.discard(result.key)
        image = QImage(
            result.mask, result.size, result.size, result.size, QImage.Format.Format_Indexed8
        ).copy()
        image.setColorTable(
            [QColor(self._palette.graph_bg).rgb(), QColor(self._palette.graph_ink).rgb()]
        )
        if len(self._tiles) > 420:
            self._tiles.clear()
        self._tiles[result.key] = image
        self.update()

    def _draw_tiles(self, painter: QPainter):
        sx, sy, u0, v0, tw, th = self._tile_geometry()
        plot_w, plot_h = self._plot_size()
        i0 = math.floor(u0 / tw)
        i1 = math.floor((u0 + plot_w / sx) / tw)
        j0 = math.floor(v0 / th)
        j1 = math.floor((v0 + plot_h / sy) / th)
        painter.save()
        painter.setClipRect(self._plot_rect())
        ink = QColor(self._palette.graph_ink)
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                image = self._tiles.get((i, j))
                origin = self.world_to_screen(i * tw, j * th)
                if image is not None:
                    painter.drawImage(
                        QRectF(origin.x(), origin.y(), TILE + 0.4, TILE + 0.4), image
                    )
                else:
                    painter.fillRect(
                        QRectF(origin.x(), origin.y(), TILE, TILE),
                        QColor(ink.red(), ink.green(), ink.blue(), 6),
                    )
        painter.restore()
        self._ensure_tiles()

    # ------------------------------------------------------------------ paint
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        painter.fillRect(self.rect(), QColor(self._palette.graph_bg))

        if self._flight is not None:
            self._draw_flight(painter)
            painter.end()
            return

        self._draw_tiles(painter)
        self._draw_cell_grid(painter)
        self._draw_frame(painter)
        self._draw_axes(painter)
        self._draw_cursor(painter)
        self._draw_corner_hud(painter)
        if self._flash > 0:
            painter.setPen(QPen(QColor(self._palette.accent), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self.rect().adjusted(2, 2, -3, -3))
        painter.end()

    def _draw_cell_grid(self, painter: QPainter):
        sx, sy = self._sx(), self._sy()
        if sx < 5.0 or sy < 5.0:
            return
        plot = self._plot_rect()
        painter.save()
        painter.setClipRect(plot)
        u0 = self._cu - plot.width() / 2 / sx
        u1 = u0 + plot.width() / sx
        v0 = self._cv - plot.height() / 2 / sy
        v1 = v0 + plot.height() / sy
        color = QColor(self._palette.graph_grid)
        color.setAlpha(120)
        painter.setPen(QPen(color, 1))
        for u in range(math.floor(u0), math.ceil(u1) + 1):
            x = self.world_to_screen(u, 0).x()
            painter.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        for v in range(math.floor(v0), math.ceil(v1) + 1):
            y = self.world_to_screen(0, v).y()
            painter.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
        painter.restore()

    def _draw_frame(self, painter: QPainter):
        top_left = self.world_to_screen(0, 0)
        bottom_right = self.world_to_screen(WIDTH, HEIGHT)
        frame = QRectF(top_left, bottom_right).normalized()
        plot = self._plot_rect()
        if not frame.intersects(plot):
            return
        accent = QColor(self._palette.accent)

        painter.save()
        painter.setClipRect(plot)
        painter.setPen(QPen(accent, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(frame)
        painter.setPen(QPen(accent, 3))
        span = 9
        for x, sx_dir in ((frame.left(), 1), (frame.right(), -1)):
            for y, sy_dir in ((frame.top(), 1), (frame.bottom(), -1)):
                painter.drawLine(QPointF(x, y), QPointF(x + span * sx_dir, y))
                painter.drawLine(QPointF(x, y), QPointF(x, y + span * sy_dir))
        painter.restore()

        if plot.left() <= frame.left() <= self.width() - 140:
            if frame.top() > 30:
                self._badge(painter, "Y = K ... K+16", frame.left(), frame.top() - 24)
            elif frame.top() >= plot.top():
                self._badge(painter, "Y = K ... K+16", frame.left() + 6, frame.top() + 5)

        plot_bottom = plot.bottom()
        if plot.left() + 140 <= frame.right() <= self.width():
            if frame.bottom() < plot_bottom - 28:
                self._badge(
                    painter, "X = 0 ... 105", frame.right() - 124, frame.bottom() + 4
                )
            elif frame.bottom() <= plot_bottom:
                self._badge(
                    painter, "X = 0 ... 105", frame.right() - 124, frame.bottom() - 24
                )

    def _badge(self, painter: QPainter, text: str, x: float, y: float, ink: bool = False):
        font = spaced_font(self._family, 8, QFont.Weight.Bold, 1.2)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        width = metrics.horizontalAdvance(text) + 12
        height = 18.0
        x = max(PLOT_LEFT + 4, min(x, self.width() - width - 4))
        y = max(4.0, min(y, self.height() - PLOT_BOTTOM - height - 4))
        palette = self._palette
        if ink:
            painter.fillRect(QRectF(x, y, width, height), QColor(palette.graph_bg))
            painter.setPen(QPen(QColor(palette.dim), 1))
            painter.drawRect(QRectF(x, y, width, height))
            painter.setPen(QColor(palette.graph_ink))
        else:
            painter.fillRect(QRectF(x, y, width, height), QColor(palette.accent))
            painter.setPen(QColor("#000000"))
        painter.drawText(
            QRectF(x, y, width, height), Qt.AlignmentFlag.AlignCenter, text
        )

    def _draw_axes(self, painter: QPainter):
        width, height = self.width(), self.height()
        plot = self._plot_rect()
        axis_color = QColor(self._palette.graph_axis)
        painter.fillRect(QRectF(0, 0, PLOT_LEFT, height), QColor(self._palette.graph_bg))
        painter.fillRect(
            QRectF(0, height - PLOT_BOTTOM, width, PLOT_BOTTOM),
            QColor(self._palette.graph_bg),
        )
        painter.setPen(QPen(axis_color, 1))
        painter.drawLine(QPointF(PLOT_LEFT, 0), QPointF(PLOT_LEFT, plot.bottom()))
        painter.drawLine(
            QPointF(PLOT_LEFT, plot.bottom()), QPointF(width, plot.bottom())
        )

        font = spaced_font(self._family, 8, QFont.Weight.Normal, 0.6)
        painter.setFont(font)

        # x ticks: display u maps to formula x = 105 - u (axes reversed)
        sx = self._sx()
        step = _nice_step(70.0 / sx)
        u0 = self._cu - plot.width() / 2 / sx
        u1 = u0 + plot.width() / sx
        for tick in self._ticks(u0, u1, step):
            formula_x = int(round(WIDTH - 1 - tick))
            if not 0 <= formula_x < WIDTH:
                continue
            x = self.world_to_screen(tick, 0).x()
            if x < PLOT_LEFT + 8 or x > width - 214:
                continue
            painter.setPen(QPen(axis_color, 1))
            painter.drawLine(QPointF(x, plot.bottom()), QPointF(x, plot.bottom() + 4))
            painter.setPen(QColor(self._palette.dim))
            painter.drawText(
                QRectF(x - 20, plot.bottom() + 5, 40, 16),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                str(formula_x),
            )

        # y ticks: offsets from K
        sy = self._sy()
        step = _nice_step(46.0 / sy)
        v0 = self._cv - plot.height() / 2 / sy
        v1 = v0 + plot.height() / sy
        for tick in self._ticks(v0, v1, step):
            y = self.world_to_screen(0, tick).y()
            if y < 14 or y > plot.bottom() - 6:
                continue
            painter.setPen(QPen(axis_color, 1))
            painter.drawLine(QPointF(PLOT_LEFT - 4, y), QPointF(PLOT_LEFT, y))
            painter.setPen(QColor(self._palette.dim))
            painter.drawText(
                QRectF(6, y - 8, PLOT_LEFT - 16, 16),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                _offset_label(int(round(tick))),
            )

        self._badge(painter, "Y = K + OFFSET", PLOT_LEFT + 10, 6, ink=True)
        painter.setFont(spaced_font(self._family, 8, QFont.Weight.Bold, 1.5))
        painter.setPen(QColor(self._palette.accent))
        painter.drawText(
            QRectF(width - 206, plot.bottom() + 5, 202, 16),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            "X (AXES REVERSED)",
        )
        if self._sy() < 1.0:
            painter.setFont(spaced_font(self._family, 8, QFont.Weight.Bold, 1.0))
            painter.setPen(QColor(self._palette.dim))
            painter.drawText(
                QRectF(PLOT_LEFT + 10, 30, 300, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "NOISE FIELD // OTHER BITMAPS",
            )

    @staticmethod
    def _ticks(start: float, end: float, step: float):
        first = math.ceil(start / step) * step
        count = int((end - first) / step) + 1
        return [first + i * step for i in range(max(0, min(count, 400)))]

    def _draw_cursor(self, painter: QPainter):
        if self._hover.x() < 0 or self._panning:
            return
        plot = self._plot_rect()
        if not plot.contains(self._hover):
            return
        accent = QColor(self._palette.accent)
        faded = QColor(accent)
        faded.setAlpha(90)
        painter.save()
        painter.setClipRect(plot)
        painter.setPen(QPen(faded, 1))
        painter.drawLine(
            QPointF(self._hover.x(), plot.top()), QPointF(self._hover.x(), plot.bottom())
        )
        painter.drawLine(
            QPointF(plot.left(), self._hover.y()), QPointF(plot.right(), self._hover.y())
        )
        painter.setPen(QPen(accent, 2))
        painter.drawLine(
            QPointF(self._hover.x() - 5, self._hover.y()),
            QPointF(self._hover.x() + 5, self._hover.y()),
        )
        painter.drawLine(
            QPointF(self._hover.x(), self._hover.y() - 5),
            QPointF(self._hover.x(), self._hover.y() + 5),
        )
        painter.restore()

        u, v = self.screen_to_world(self._hover)
        col = math.floor(u)
        offset = math.floor(v)
        d, row = divmod(offset, 17)
        n = self._n_ref + d
        bit = cell_is_black(n, col, row)
        x_text = WIDTH - 1 - col if 0 <= col < WIDTH else col
        text = f"X {x_text:>3}  Y K{offset:+d}  BIT {bit}"
        font = spaced_font(self._family, 8, QFont.Weight.Bold, 0.8)
        painter.setFont(font)
        metrics = QFontMetricsF(font)
        width = metrics.horizontalAdvance(text) + 12
        bx = min(self._hover.x() + 14, self.width() - width - 4)
        by = min(self._hover.y() + 14, plot.bottom() - 22)
        painter.fillRect(QRectF(bx, by, width, 18), QColor(self._palette.graph_bg))
        painter.setPen(QPen(accent, 1))
        painter.drawRect(QRectF(bx, by, width, 18))
        painter.setPen(accent)
        painter.drawText(QRectF(bx, by, width, 18), Qt.AlignmentFlag.AlignCenter, text)

    def _draw_corner_hud(self, painter: QPainter):
        painter.setFont(spaced_font(self._family, 8, QFont.Weight.Bold, 1.0))
        text = f"{self._sy():0.2f} PX/ROW  //  K {len(str(self._k))} DIGITS"
        metrics = QFontMetricsF(painter.font())
        width = metrics.horizontalAdvance(text) + 12
        rect = QRectF(self.width() - width - 8, 6, width, 17)
        painter.fillRect(rect, QColor(self._palette.graph_bg))
        painter.setPen(QColor(self._palette.dim))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        if self._pending and not self._tiles:
            painter.setFont(spaced_font(self._family, 8, QFont.Weight.Bold, 1.5))
            painter.setPen(QColor(self._palette.accent))
            painter.drawText(
                QRectF(PLOT_LEFT + 10, 32, 400, 18),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                "COMPUTING FORMULA ...",
            )

    # ------------------------------------------------------------------ flight
    def find_image(self):
        if self._flight_timer.isActive():
            return
        self._flight = {"step": 0, "total": 34}
        self._flight_timer.start()
        self._invalidate()
        self.status.emit("[ FLIGHT ] SCANNING Y = 0 ... K // LOG SCALE")

    def _flight_tick(self):
        flight = self._flight
        if flight is None:
            self._flight_timer.stop()
            return
        flight["step"] += 1
        if flight["step"] >= flight["total"]:
            self._flight_timer.stop()
            self._flight = None
            self.reset_view()
            self._flash = 5
            self._flash_timer.start()
            self.status.emit("[ LOCKED ] IMAGE FOUND AT Y = K ... K+16")
            self.update()
            return
        self.update()

    def _flash_tick(self):
        self._flash -= 1
        if self._flash <= 0:
            self._flash = 0
            self._flash_timer.stop()
        self.update()

    def _draw_flight(self, painter: QPainter):
        flight = self._flight
        assert flight is not None
        progress = flight["step"] / flight["total"]
        log_max = _log10_big(self._n_ref)
        log_n = log_max * progress
        exponent = int(log_n)
        fraction = log_n - exponent
        n = max(1, int(10**fraction) * 10**exponent)
        bitmap = decode_n(n)
        y_value = 17 * n

        mask = bytearray(WIDTH * HEIGHT)
        for row in range(HEIGHT):
            base = row * WIDTH
            for col in range(WIDTH):
                if bitmap[row][col]:
                    mask[base + col] = 1
        image = QImage(bytes(mask), WIDTH, HEIGHT, WIDTH, QImage.Format.Format_Indexed8).copy()
        image.setColorTable(
            [QColor(self._palette.graph_bg).rgb(), QColor(self._palette.graph_ink).rgb()]
        )

        area_w = self.width() - 120
        area_h = self.height() - 180
        cell = max(1, min(area_w // WIDTH, area_h // HEIGHT))
        target_w = WIDTH * cell
        target_h = HEIGHT * cell
        x = (self.width() - target_w) / 2
        y = (self.height() - target_h) / 2 - 10

        accent = QColor(self._palette.accent)
        painter.setPen(QPen(accent, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(x - 4, y - 4, target_w + 8, target_h + 8))
        painter.drawImage(QRectF(x, y, target_w, target_h), image)
        if cell >= 6:
            painter.setPen(QPen(QColor(self._palette.graph_grid), 1))
            for i in range(1, WIDTH):
                painter.drawLine(
                    QPointF(x + i * cell, y), QPointF(x + i * cell, y + target_h)
                )
            for j in range(1, HEIGHT):
                painter.drawLine(
                    QPointF(x, y + j * cell), QPointF(x + target_w, y + j * cell)
                )

        painter.setFont(spaced_font(self._family, 20, QFont.Weight.Bold, 3.0))
        painter.setPen(accent)
        painter.drawText(
            QRectF(24, 18, self.width() - 48, 34),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "[ LOCATING ]",
        )
        painter.setFont(spaced_font(self._family, 12, QFont.Weight.Bold, 1.5))
        painter.setPen(QColor(self._palette.graph_ink))
        painter.drawText(
            QRectF(24, 52, self.width() - 48, 24),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"Y = {_sci(y_value)}",
        )
        painter.setFont(spaced_font(self._family, 9, QFont.Weight.Normal, 0.8))
        painter.setPen(QColor(self._palette.dim))
        painter.drawText(
            QRectF(24, 76, self.width() - 48, 20),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"N = FLOOR(Y/17) = {_sci(n)}   //   MAGNITUDE 10^{exponent}",
        )

        bar = QRectF(24, self.height() - 46, 320, 12)
        painter.setPen(QPen(QColor(self._palette.graph_axis), 1))
        painter.drawRect(bar)
        steps = 24
        filled = int(progress * steps) / steps
        painter.fillRect(
            QRectF(bar.x() + 2, bar.y() + 2, (bar.width() - 4) * filled, bar.height() - 4),
            accent,
        )
        painter.setFont(spaced_font(self._family, 8, QFont.Weight.Bold, 1.0))
        painter.setPen(QColor(self._palette.dim))
        painter.drawText(
            QRectF(24, self.height() - 28, self.width() - 48, 18),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "REAL FORMULA / BIG INTEGERS -- NO PRECOMPUTED BITMAP",
        )

        ladder_x = self.width() - 62
        painter.setPen(QPen(QColor(self._palette.graph_axis), 1))
        painter.drawLine(QPointF(ladder_x, 120), QPointF(ladder_x, self.height() - 80))
        painter.setFont(spaced_font(self._family, 8, QFont.Weight.Normal, 0.5))
        for i in range(7):
            tick_log = log_max * (1 - i / 6)
            ty = 120 + (self.height() - 200) * (i / 6)
            painter.setPen(QPen(QColor(self._palette.graph_axis), 1))
            painter.drawLine(QPointF(ladder_x, ty), QPointF(ladder_x + 5, ty))
            painter.setPen(QColor(self._palette.dim))
            painter.drawText(
                QRectF(ladder_x + 10, ty - 8, 52, 16),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                f"10^{int(tick_log)}",
            )
        marker = 120 + (self.height() - 200) * (log_n / log_max if log_max else 0)
        painter.fillRect(QRectF(ladder_x - 5, marker - 4, 10, 8), accent)

    # ------------------------------------------------------------------ input
    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        if delta == 0:
            return
        self.zoom_at(event.position(), 1.25 if delta > 0 else 0.8)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._panning = True
            self._pan_anchor = event.position()
            self._pan_center = (self._cu, self._cv)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            self.reset_view()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        self._hover = event.position()
        if self._panning:
            dx = event.position().x() - self._pan_anchor.x()
            dy = event.position().y() - self._pan_anchor.y()
            if self._sx() > self._fit_sx() + 0.01:
                self._cu = max(
                    0.0, min(float(WIDTH), self._pan_center[0] - dx / self._sx())
                )
            self._cv = max(-1e9, min(1e9, self._pan_center[1] - dy / self._sy()))
        u, v = self.screen_to_world(event.position())
        col = math.floor(u)
        offset = math.floor(v)
        d, row = divmod(offset, 17)
        n = self._n_ref + d
        bit = cell_is_black(n, col, row)
        x_text = WIDTH - 1 - col if 0 <= col < WIDTH else col
        text = f"X {x_text:>3} | Y K{offset:+d} | BIT {bit} | {self._sy():0.2f} PX/ROW"
        if text != self._hover_text:
            self._hover_text = text
            self.probe.emit(text)
        self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.CrossCursor)
            self.update()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        self._hover = QPointF(-1, -1)
        self.probe.emit("")
        self.update()
        super().leaveEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._needs_fit and self.width() > 400 and self.height() > 300:
            self._needs_fit = False
            self.reset_view()
            return
        if self._at_fit:
            self._zoom = min(MAX_ZOOM, self._fit_sx())
            self._cu = WIDTH / 2
            self._cv = HEIGHT / 2
            self._invalidate()
        else:
            self._invalidate()
        self.update()

    def shutdown(self):
        self._flight_timer.stop()
        self._flash_timer.stop()
        self._pool.clear()
        self._pool.waitForDone(3000)

    def save_png(self, path: str) -> bool:
        return self.grab().save(path, "PNG")
