"""Application entry point."""

from __future__ import annotations

import sys
import tempfile
import time
import traceback
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .core.tupper import ORIGINAL_K, decode, encode
from .ui.main_window import MainWindow
from .ui.theme import asset, base_font, load_fonts


def _selftest(app: QApplication) -> int:
    """Headless-ish smoke test used to validate the frozen executable."""
    lines: list[str] = []
    ok = True
    try:
        bitmap = decode(ORIGINAL_K)
        lines.append(f"decode rows={len(bitmap)} cols={len(bitmap[0])}")
        lines.append(f"roundtrip={encode(bitmap) == ORIGINAL_K}")
        ok = ok and encode(bitmap) == ORIGINAL_K
        family = load_fonts()
        lines.append(f"font={family}")
        window = MainWindow(family)
        window.resize(1480, 950)
        window.show()
        app.processEvents()
        deadline = time.time() + 8
        while time.time() < deadline and (not window.graph._tiles or window.graph._pending):
            app.processEvents()
            time.sleep(0.04)
        window.graph.zoom_step(2.0)
        deadline = time.time() + 8
        while time.time() < deadline and (not window.graph._tiles or window.graph._pending):
            app.processEvents()
            time.sleep(0.04)
        # give the queued repaint a chance to fill the last visible tiles
        settle = time.time() + 1.2
        while time.time() < settle:
            app.processEvents()
            time.sleep(0.04)
        out = Path(tempfile.gettempdir()) / "tupper_selftest.png"
        saved = window.grab().save(str(out), "PNG")
        lines.append(f"screenshot={saved} {out}")
        lines.append(f"graph_tiles={len(window.graph._tiles)}")
        ok = ok and saved
        window.close()
        app.processEvents()
    except Exception:
        lines.append(traceback.format_exc())
        ok = False
    report = Path(tempfile.gettempdir()) / "tupper_selftest.txt"
    report.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    if "--selftest" in argv:
        app = QApplication(argv)
        app.setApplicationName("TUPPER")
        app.setStyle("Fusion")
        return _selftest(app)

    app = QApplication(argv)
    app.setApplicationName("TUPPER")
    app.setOrganizationName("TUPPER")
    app.setStyle("Fusion")
    family = load_fonts()
    app.setFont(base_font(family))
    icon = QIcon(str(asset("tupper.ico")))
    app.setWindowIcon(icon)

    window = MainWindow(family)
    window.setWindowIcon(icon)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
