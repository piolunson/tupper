"""Image -> 106x17 bitmap pipeline (Pillow only, no Qt)."""

from __future__ import annotations

from PIL import Image

from .tupper import Bitmap, HEIGHT, WIDTH

DITHER_MODES = ("NONE", "FLOYD-STEINBERG", "BAYER 4", "BAYER 8")

_BAYER4 = (
    (0, 8, 2, 10),
    (12, 4, 14, 6),
    (3, 11, 1, 9),
    (15, 7, 13, 5),
)


def _bayer_matrix(size: int) -> list[list[int]]:
    if size == 4:
        return [list(row) for row in _BAYER4]
    base = _bayer_matrix(size // 2)
    half = size // 2
    out = [[0] * size for _ in range(size)]
    for y in range(half):
        for x in range(half):
            v = base[y][x] * 4
            out[y][x] = v
            out[y][x + half] = v + 2
            out[y + half][x] = v + 3
            out[y + half][x + half] = v + 1
    return out


_BAYER8 = _bayer_matrix(8)


def letterbox(image: Image.Image, width: int = WIDTH, height: int = HEIGHT) -> Image.Image:
    """Scale to fit, preserving aspect ratio, and centre on a white canvas."""
    gray = image.convert("L")
    box = (width, height)
    contained = gray.copy()
    contained.thumbnail(box, Image.Resampling.LANCZOS)
    canvas = Image.new("L", box, 255)
    canvas.paste(contained, ((width - contained.width) // 2, (height - contained.height) // 2))
    return canvas


def _floyd_steinberg(gray: Image.Image, threshold: int) -> Bitmap:
    w, h = gray.size
    values = [float(v) for v in gray.getdata()]
    out = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            i = y * w + x
            old = values[i]
            new = 0.0 if old < threshold else 255.0
            out[y][x] = 1 if new == 0.0 else 0
            err = old - new
            if x + 1 < w:
                values[i + 1] += err * 7 / 16
            if y + 1 < h:
                if x > 0:
                    values[i + w - 1] += err * 3 / 16
                values[i + w] += err * 5 / 16
                if x + 1 < w:
                    values[i + w + 1] += err / 16
    return out


def _ordered(gray: Image.Image, threshold: int, matrix: list[list[int]]) -> Bitmap:
    w, h = gray.size
    n = len(matrix)
    span = n * n
    flat = list(gray.getdata())
    bias = threshold - 128
    out = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            level = (matrix[y % n][x % n] + 0.5) / span * 255.0
            out[y][x] = 1 if flat[y * w + x] < level + bias else 0
    return out


def _plain(gray: Image.Image, threshold: int) -> Bitmap:
    w, h = gray.size
    flat = list(gray.getdata())
    return [
        [1 if flat[y * w + x] < threshold else 0 for x in range(w)]
        for y in range(h)
    ]


def process(
    image: Image.Image,
    threshold: int = 128,
    dither: str = "NONE",
    invert: bool = False,
    width: int = WIDTH,
    height: int = HEIGHT,
) -> Bitmap:
    """Threshold/dither an arbitrary image into a ``height`` x ``width`` bitmap.

    Dark pixels become ink (1).  The image is letterboxed on white first, so an
    aspect-ratio mismatch leaves a clean border instead of stretching.
    """
    if dither not in DITHER_MODES:
        raise ValueError(f"unknown dither mode: {dither}")
    gray = letterbox(image, width, height)
    mode = dither.upper()
    if mode == "FLOYD-STEINBERG":
        bitmap = _floyd_steinberg(gray, threshold)
    elif mode == "BAYER 4":
        bitmap = _ordered(gray, threshold, _BAYER4)
    elif mode == "BAYER 8":
        bitmap = _ordered(gray, threshold, _BAYER8)
    else:
        bitmap = _plain(gray, threshold)
    if invert:
        bitmap = [[0 if cell else 1 for cell in row] for row in bitmap]
    return bitmap


def bitmap_to_image(bitmap: Bitmap, scale: int = 1, invert: bool = False) -> Image.Image:
    """Render a bitmap as a monochrome Pillow image (nearest-neighbour upscale)."""
    if scale < 1:
        raise ValueError("scale must be >= 1")
    height = len(bitmap)
    width = len(bitmap[0]) if height else 0
    ink = 255 if invert else 0
    paper = 0 if invert else 255
    image = Image.new("L", (width, height), paper)
    pixel = image.load()
    for y, row in enumerate(bitmap):
        for x, cell in enumerate(row):
            if cell:
                pixel[x, y] = ink
    if scale != 1:
        image = image.resize((width * scale, height * scale), Image.Resampling.NEAREST)
    return image.convert("RGB")
