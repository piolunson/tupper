"""TUPPER main window: terminal-sheet layout around the formula graph."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QGuiApplication,
    QImage,
    QKeySequence,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from ..core import imaging
from ..core.presets import PRESETS
from ..core.tupper import (
    ORIGINAL_K,
    decode,
    encode,
    empty_bitmap,
    parse_k,
)
from .graph import GraphView
from .theme import DARK, LIGHT, Palette, spaced_font, stylesheet
from .widgets import (
    FramelessWindow,
    KField,
    PixelCanvas,
    SectionHeader,
    TitleBar,
    button,
    dim_label,
    hline,
    label,
)

IMAGE_FILTER = "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.tif *.tiff);;All files (*)"
TEXT_FILTER = "Text (*.txt);;All files (*)"


def pil_from_qimage(image: QImage) -> Image.Image:
    converted = image.convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = converted.width(), converted.height()
    buffer = converted.constBits().tobytes()
    return Image.frombytes(
        "RGBA", (width, height), buffer, "raw", "RGBA", converted.bytesPerLine()
    )


class MainWindow(FramelessWindow):
    def __init__(self, family: str):
        super().__init__(family)
        self._family = family
        self._palette: Palette = DARK
        self._source: Image.Image | None = None
        self._k = ORIGINAL_K
        self._building = True
        self.setObjectName("Root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle("TUPPER")
        self.setAcceptDrops(True)
        self.setMinimumSize(1180, 700)
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.resize(
                min(1480, max(1180, available.width() - 60)),
                min(950, max(700, available.height() - 60)),
            )
        else:
            self.resize(1480, 950)

        self._build()
        self._apply_theme(DARK)
        self._building = False
        self._bind_shortcuts()
        self._show_k(ORIGINAL_K, animate=True)
        self._status("[ READY ] TUPPER'S SELF-REFERENTIAL DECODER // ORIGINAL K LOADED")

    # ------------------------------------------------------------------ build
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(6)

        self.title_bar = TitleBar(
            self,
            self._family,
            self._palette,
            "TUPPER",
            "// SELF-REFERENTIAL GRAPHICS TERMINAL // OFFLINE",
        )
        self.title_bar.invert_btn.clicked.connect(self.toggle_theme)
        root.addWidget(self.title_bar)

        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(6)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(self._build_import_panel(), 5)
        row.addWidget(self._build_encode_panel(), 4)
        row_widget = QWidget()
        row_widget.setLayout(row)
        row_widget.setFixedHeight(280)
        content.addWidget(row_widget)

        content.addWidget(self._build_graph_panel(), 1)
        root.addLayout(content, 1)
        root.addWidget(self._build_status_bar())

    def _build_import_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(8)
        header.addWidget(
            SectionHeader("01", "IMPORT", "106 X 17 / 1-BIT / LETTERBOXED", self._family, self._palette),
            1,
        )
        layout.addLayout(header)

        self.canvas = PixelCanvas(self._family, self._palette)
        self.canvas.set_placeholder("DROP IMAGE  /  CTRL+V  /  [ OPEN ]")
        self.canvas.edited.connect(self._canvas_edited)
        self.canvas.hovered.connect(self._canvas_hover)
        self.canvas.setFixedHeight(140)
        layout.addWidget(self.canvas)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)
        controls.addWidget(dim_label("THRESH", self._family))
        self.threshold = QSlider(Qt.Orientation.Horizontal)
        self.threshold.setRange(0, 255)
        self.threshold.setValue(128)
        self.threshold.setFixedWidth(130)
        self.threshold.valueChanged.connect(self._threshold_changed)
        controls.addWidget(self.threshold)
        self.threshold_value = label("128", "Readout", self._family)
        self.threshold_value.setFixedWidth(28)
        controls.addWidget(self.threshold_value)
        controls.addSpacing(6)
        controls.addWidget(dim_label("DITHER", self._family))
        self.dither = QComboBox()
        self.dither.addItems(imaging.DITHER_MODES)
        self.dither.setCurrentText("FLOYD-STEINBERG")
        self.dither.setFixedWidth(158)
        self.dither.currentTextChanged.connect(self._threshold_changed)
        controls.addWidget(self.dither)
        controls.addStretch(1)
        self.negate_btn = button("[ NEG ]", self._family, tooltip="Invert the 106x17 bitmap")
        self.negate_btn.setCheckable(True)
        self.negate_btn.clicked.connect(self._threshold_changed)
        controls.addWidget(self.negate_btn)
        layout.addLayout(controls)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)
        self.open_btn = button("[ OPEN IMAGE ]", self._family, tooltip="Ctrl+O")
        self.open_btn.clicked.connect(self.open_image)
        self.paste_btn = button("[ PASTE ]", self._family, tooltip="Ctrl+V")
        self.paste_btn.clicked.connect(self.paste_from_clipboard)
        self.clear_btn = button("[ CLEAR ]", self._family, tooltip="Blank 106x17 bitmap")
        self.clear_btn.clicked.connect(self.clear_bitmap)
        actions.addWidget(self.open_btn)
        actions.addWidget(self.paste_btn)
        actions.addWidget(self.clear_btn)
        actions.addStretch(1)
        actions.addWidget(dim_label("PNG", self._family))
        self.scale_combo = QComboBox()
        self.scale_combo.addItems(["X8", "X16"])
        self.scale_combo.setFixedWidth(70)
        actions.addWidget(self.scale_combo)
        self.export_btn = button("[ EXPORT PNG ]", self._family, "Primary", "Ctrl+S")
        self.export_btn.clicked.connect(self.export_image_png)
        actions.addWidget(self.export_btn)
        layout.addLayout(actions)
        return panel

    def _build_encode_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        self.encode_header = SectionHeader(
            "02", "ENCODE", "K = 17N", self._family, self._palette
        )
        layout.addWidget(self.encode_header)

        self.k_field = KField(self._family)
        self.k_field.setPlaceholderText("[ K APPEARS HERE ]")
        layout.addWidget(self.k_field)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.digits_label = label("0 DIGITS", "Dim", self._family)
        row.addWidget(self.digits_label)
        row.addStretch(1)
        self.copy_btn = button("[ COPY K ]", self._family, tooltip="Ctrl+C")
        self.copy_btn.clicked.connect(self.copy_k)
        self.save_k_btn = button("[ SAVE .TXT ]", self._family)
        self.save_k_btn.clicked.connect(self.save_k_file)
        self.load_k_btn = button("[ LOAD .TXT ]", self._family)
        self.load_k_btn.clicked.connect(self.load_k_file)
        row.addWidget(self.copy_btn)
        row.addWidget(self.save_k_btn)
        row.addWidget(self.load_k_btn)
        layout.addLayout(row)

        layout.addWidget(hline(self._palette))

        decode_row = QHBoxLayout()
        decode_row.setContentsMargins(0, 0, 0, 0)
        decode_row.setSpacing(6)
        decode_row.addWidget(label("[ DECODE ]", "Section", self._family))
        self.preset = QComboBox()
        self.preset.addItem("PRESETS //")
        for name, _k in PRESETS:
            self.preset.addItem(name)
        self.preset.activated.connect(self._preset_chosen)
        decode_row.addWidget(self.preset, 1)
        layout.addLayout(decode_row)

        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 0, 0, 0)
        input_row.setSpacing(6)
        self.decode_input = QLineEdit()
        self.decode_input.setPlaceholderText("[ PASTE K / DIGITS ]")
        self.decode_input.returnPressed.connect(self.decode_from_input)
        self.decode_btn = button("[ RUN ]", self._family, "Primary")
        self.decode_btn.clicked.connect(self.decode_from_input)
        input_row.addWidget(self.decode_input, 1)
        input_row.addWidget(self.decode_btn)
        layout.addLayout(input_row)
        layout.addStretch(1)
        return panel

    def _build_graph_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        top.addWidget(
            SectionHeader("03", "LOCATE", "WHERE IS THE IMAGE", self._family, self._palette),
            1,
        )
        self.find_btn = button("[ FIND IMAGE ]", self._family, "Primary", "F")
        self.find_btn.clicked.connect(self.find_image)
        self.reset_btn = button("[ RESET ]", self._family, tooltip="Space")
        self.reset_btn.clicked.connect(self.reset_view)
        self.zoom_out_btn = button("-", self._family, tooltip="Zoom out")
        self.zoom_out_btn.setFixedWidth(30)
        self.zoom_out_btn.clicked.connect(lambda: self.graph.zoom_step(0.8))
        self.zoom_in_btn = button("+", self._family, tooltip="Zoom in")
        self.zoom_in_btn.setFixedWidth(30)
        self.zoom_in_btn.clicked.connect(lambda: self.graph.zoom_step(1.25))
        self.save_graph_btn = button("[ SAVE GRAPH PNG ]", self._family)
        self.save_graph_btn.clicked.connect(self.export_graph_png)
        for widget in (
            self.find_btn,
            self.reset_btn,
            self.zoom_out_btn,
            self.zoom_in_btn,
            self.save_graph_btn,
        ):
            top.addWidget(widget)
        layout.addLayout(top)

        shell = QFrame()
        shell.setObjectName("GraphShell")
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(2, 2, 2, 2)
        shell_layout.setSpacing(0)
        self.graph = GraphView(self._family, self._palette)
        self.graph.status.connect(self._status)
        self.graph.probe.connect(self._probe)
        shell_layout.addWidget(self.graph)
        layout.addWidget(shell, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(8)
        footer.addWidget(
            dim_label("WHEEL ZOOM / DRAG PAN / F FIND / SPACE RESET", self._family)
        )
        footer.addStretch(1)
        footer.addWidget(
            dim_label("FRAME = X 0..105 / Y K..K+16 // AXES REVERSED", self._family)
        )
        layout.addLayout(footer)
        return panel

    def _build_status_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("StatusBar")
        bar.setFixedHeight(26)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)
        self.status_label = label("", "Readout", self._family)
        self.status_label.setFont(spaced_font(self._family, 8, QFont.Weight.Normal, 0.6))
        self.probe_label = label("", "StatusText", self._family)
        self.probe_label.setFont(spaced_font(self._family, 8, QFont.Weight.Normal, 0.6))
        layout.addWidget(self.status_label, 1)
        layout.addWidget(self.probe_label)
        return bar

    # ------------------------------------------------------------------ theme
    def _apply_theme(self, palette: Palette):
        self._palette = palette
        self.setStyleSheet(stylesheet(palette, self._family))
        self.canvas.set_palette(palette)
        if hasattr(self, "graph"):
            self.graph.set_palette(palette)
        if hasattr(self, "title_bar"):
            self.title_bar._palette = palette
            self.title_bar.invert_btn.setChecked(palette.inverted)
        self.update()

    def toggle_theme(self):
        target = LIGHT if not self._palette.inverted else DARK
        self._apply_theme(target)
        self._status(
            "[ THEME ] WHITE SHEET" if target.inverted else "[ THEME ] DARK TERMINAL"
        )

    # ------------------------------------------------------------------ state
    def _status(self, text: str):
        self.status_label.setText(text)

    def _probe(self, text: str):
        self.probe_label.setText(text if text else "CURSOR OUTSIDE")

    def _canvas_hover(self, row: int, col: int):
        if row < 0:
            return
        value = self.canvas.bitmap()[row][col]
        self.probe_label.setText(f"CELL X {col:>3} / Y {row:>2} / BIT {value}")

    def _show_k(self, k: int, animate: bool):
        self._k = k
        text = str(k)
        self.canvas.set_bitmap(decode(k))
        self.k_field.set_text(text, animate=animate)
        self.digits_label.setText(f"{len(text)} DIGITS")
        self.graph.set_k(k)

    def _canvas_edited(self):
        self._commit_bitmap(reset=False)
        self._status("[ EDIT ] BITMAP MODIFIED // K RECOMPUTED")

    def _commit_bitmap(self, reset: bool):
        k = encode(self.canvas.bitmap())
        self._k = k
        self.k_field.set_text(str(k), animate=False)
        self.digits_label.setText(f"{len(str(k))} DIGITS")
        self.graph.set_k(k, reset=reset)

    def _current_k(self) -> int:
        return self._k

    # ------------------------------------------------------------------ import
    def _set_source(self, image: Image.Image, note: str):
        upright = ImageOps.exif_transpose(image).convert("RGBA")
        flat = Image.new("RGBA", upright.size, (255, 255, 255, 255))
        flat.alpha_composite(upright)
        self._source = flat.convert("RGB")
        self._render_source()
        size = f"{self._source.width}X{self._source.height}"
        self._status(f"[ IMPORT ] {note} {size} // LETTERBOX 106X17")

    def _render_source(self):
        if self._source is None:
            return
        bitmap = imaging.process(
            self._source,
            threshold=self.threshold.value(),
            dither=self.dither.currentText(),
            invert=self.negate_btn.isChecked(),
        )
        self.canvas.set_bitmap(bitmap)
        self._commit_bitmap(reset=True)

    def _threshold_changed(self, *_):
        self.threshold_value.setText(str(self.threshold.value()))
        if self._source is not None:
            self._render_source()
        elif self.negate_btn.isChecked():
            bitmap = [[0 if cell else 1 for cell in row] for row in self.canvas.bitmap()]
            self.canvas.set_bitmap(bitmap)
            self._canvas_edited()

    def open_image(self):
        path, _ = QFileDialog.getOpenFileName(self, "OPEN IMAGE", "", IMAGE_FILTER)
        if not path:
            return
        try:
            with Image.open(path) as image:
                self._set_source(image.copy(), Path(path).name.upper())
        except Exception as exc:
            self._status(f"[ ERROR ] CANNOT READ IMAGE // {exc}")

    def clear_bitmap(self):
        self._source = None
        self.canvas.set_bitmap(empty_bitmap())
        self._show_k(0, animate=False)
        self._status("[ CLEAR ] EMPTY BITMAP // K = 0")

    def paste_from_clipboard(self):
        clipboard = QGuiApplication.clipboard()
        image = clipboard.image()
        if image is not None and not image.isNull():
            self._set_source(pil_from_qimage(image), "CLIPBOARD")
            return
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit, QPlainTextEdit)) and not focus.isReadOnly():
            focus.paste()
            return
        text = clipboard.text().strip()
        if not text:
            self._status("[ PASTE ] CLIPBOARD IS EMPTY")
            return
        digits = "".join(ch for ch in text if ch.isdigit())
        if len(digits) < 8:
            self._status("[ PASTE ] NO IMAGE AND NO K DIGITS FOUND")
            return
        self._decode_text(text)

    def dragEnterEvent(self, event):
        mime = event.mimeData()
        if mime.hasImage() or mime.hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        mime = event.mimeData()
        if mime.hasImage():
            image = QImage(mime.imageData())
            if not image.isNull():
                self._set_source(pil_from_qimage(image), "DROPPED IMAGE")
                return
        for url in mime.urls():
            path = url.toLocalFile()
            if not path:
                continue
            suffix = Path(path).suffix.lower()
            if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}:
                try:
                    with Image.open(path) as image:
                        self._set_source(image.copy(), Path(path).name.upper())
                except Exception as exc:
                    self._status(f"[ ERROR ] CANNOT READ IMAGE // {exc}")
                return
            if suffix == ".txt":
                self._load_k_path(path)
                return
        self._status("[ DROP ] NOTHING USABLE DROPPED")

    # ------------------------------------------------------------------ encode
    def copy_k(self):
        QGuiApplication.clipboard().setText(str(self._k))
        self._status(f"[ COPY ] K // {len(str(self._k))} DIGITS ON CLIPBOARD")

    def save_k_file(self):
        path, _ = QFileDialog.getSaveFileName(self, "SAVE K", "tupper_k.txt", TEXT_FILTER)
        if not path:
            return
        try:
            Path(path).write_text(str(self._k), encoding="utf-8")
            self._status(f"[ SAVE ] K WRITTEN // {path}")
        except Exception as exc:
            self._status(f"[ ERROR ] {exc}")

    def load_k_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "LOAD K", "", TEXT_FILTER)
        if path:
            self._load_k_path(path)

    def _load_k_path(self, path: str):
        try:
            text = Path(path).read_text(encoding="utf-8", errors="ignore")
            k = parse_k(text)
        except Exception as exc:
            self._status(f"[ ERROR ] CANNOT LOAD K // {exc}")
            return
        self._show_k(k, animate=True)
        self._status(f"[ LOAD ] K FROM {Path(path).name.upper()} // {len(str(k))} DIGITS")

    def _preset_chosen(self, index: int):
        if index <= 0:
            return
        name, k = PRESETS[index - 1]
        self.preset.setCurrentIndex(0)
        self.decode_input.setText(str(k))
        self._show_k(k, animate=True)
        self._status(f"[ PRESET ] {name}")

    def decode_from_input(self):
        text = self.decode_input.text()
        if not text.strip():
            self._status("[ DECODE ] INPUT IS EMPTY")
            return
        self._decode_text(text)

    def _decode_text(self, text: str):
        try:
            k = parse_k(text)
        except ValueError as exc:
            self._status(f"[ ERROR ] INVALID K // {exc}")
            return
        self._show_k(k, animate=True)
        self._status(f"[ DECODE ] K -> 106 X 17 // {len(str(k))} DIGITS")

    # ------------------------------------------------------------------ locate
    def find_image(self):
        if isinstance(QApplication.focusWidget(), (QLineEdit, QPlainTextEdit)):
            return
        self.graph.find_image()

    def reset_view(self):
        self.graph.reset_view()
        self._status("[ VIEW ] RESET TO FRAME")

    # ------------------------------------------------------------------ export
    def _export_scale(self) -> int:
        return 16 if self.scale_combo.currentText() == "X16" else 8

    def export_image_png(self):
        scale = self._export_scale()
        default = f"tupper_106x17_x{scale}.png"
        path, _ = QFileDialog.getSaveFileName(self, "EXPORT IMAGE PNG", default, "PNG (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        try:
            image = imaging.bitmap_to_image(self.canvas.bitmap(), scale=scale)
            image.save(path)
            self._status(f"[ EXPORT ] PNG x{scale} // {path}")
        except Exception as exc:
            self._status(f"[ ERROR ] {exc}")

    def export_graph_png(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "EXPORT GRAPH PNG", "tupper_graph.png", "PNG (*.png)"
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        if self.graph.save_png(path):
            self._status(f"[ EXPORT ] GRAPH PNG // {path}")
        else:
            self._status("[ ERROR ] GRAPH SAVE FAILED")

    # ------------------------------------------------------------------ keys
    def _bind_shortcuts(self):
        for sequence, slot in (
            ("Ctrl+O", self.open_image),
            ("Ctrl+S", self.export_image_png),
            ("Ctrl+C", self.copy_k),
            ("Ctrl+V", self.paste_from_clipboard),
            ("Ctrl+I", self.toggle_theme),
        ):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(slot)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not (
            isinstance(QApplication.focusWidget(), (QLineEdit, QPlainTextEdit))
        ):
            self.reset_view()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F and not (
            isinstance(QApplication.focusWidget(), (QLineEdit, QPlainTextEdit))
        ):
            self.graph.find_image()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.graph.shutdown()
        super().closeEvent(event)
