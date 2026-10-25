"""Background tile rendering for the formula graph."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QRunnable, Signal

from ..core.tupper import plot_tile


@dataclass(frozen=True)
class TileRequest:
    key: tuple[int, int]
    epoch: int
    k: int
    u0: float
    v0: float
    scale: float
    scale_y: float
    size: int


@dataclass(frozen=True)
class TileResult:
    key: tuple[int, int]
    epoch: int
    mask: bytes
    size: int


class TileSignals(QObject):
    finished = Signal(object)


class TileTask(QRunnable):
    """Runs the big-integer formula for one tile, never on the GUI thread."""

    def __init__(self, request: TileRequest, signals: TileSignals):
        super().__init__()
        self.request = request
        self.signals = signals

    def run(self) -> None:  # pragma: no cover - exercised through the UI
        req = self.request
        try:
            mask = bytes(
                plot_tile(
                    req.k,
                    req.u0,
                    req.v0,
                    req.scale,
                    req.size,
                    req.size,
                    samples=1,
                    scale_y=req.scale_y,
                )
            )
        except Exception:
            mask = bytes(req.size * req.size)
        self.signals.finished.emit(TileResult(req.key, req.epoch, mask, req.size))
