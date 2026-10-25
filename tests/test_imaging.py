"""Tests for the image -> bitmap pipeline."""

from __future__ import annotations

from PIL import Image, ImageDraw

from app.core.imaging import DITHER_MODES, bitmap_to_image, letterbox, process
from app.core.tupper import HEIGHT, WIDTH


def _ink_count(bitmap):
    return sum(sum(row) for row in bitmap)


def _bbox(bitmap):
    rows = [i for i, row in enumerate(bitmap) if any(row)]
    cols = [j for j in range(WIDTH) if any(row[j] for row in bitmap)]
    return (min(cols), min(rows), max(cols), max(rows)) if rows else None


def test_letterbox_preserves_aspect_ratio():
    wide = Image.new("RGB", (400, 100), "black")
    box = letterbox(wide)
    assert box.size == (WIDTH, HEIGHT)
    bbox = _bbox(process(wide, threshold=128))
    assert bbox is not None
    width = bbox[2] - bbox[0] + 1
    height = bbox[3] - bbox[1] + 1
    # 4:1 source fit into 106x17 -> ~68x17, vertically full, horizontally centred
    assert height == HEIGHT
    assert 64 <= width <= 72
    assert abs(bbox[0] - (WIDTH - 1 - bbox[2])) <= 1


def test_threshold_extremes():
    white = Image.new("RGB", (200, 60), "white")
    assert _ink_count(process(white, threshold=128)) == 0
    # Exactly 106:17, so letterboxing has no margin to fill.
    black = Image.new("RGB", (WIDTH * 2, HEIGHT * 2), "black")
    assert _ink_count(process(black, threshold=128)) == WIDTH * HEIGHT
    # slider at the bottom leaves even black pixels above the threshold
    assert _ink_count(process(black, threshold=0)) == 0


def test_invert_flips_every_cell():
    image = Image.new("RGB", (212, 34), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 5, 120, 25), fill="black")
    normal = process(image, threshold=128)
    inverted = process(image, threshold=128, invert=True)
    for r in range(HEIGHT):
        for c in range(WIDTH):
            assert inverted[r][c] == (0 if normal[r][c] else 1)
    assert 100 < _ink_count(normal) < 1500


def test_all_dither_modes_produce_both_tone_levels():
    gradient = Image.new("L", (WIDTH, HEIGHT))
    for x in range(WIDTH):
        for y in range(HEIGHT):
            gradient.putpixel((x, y), int(x / (WIDTH - 1) * 255))
    for mode in DITHER_MODES:
        bitmap = process(gradient, threshold=128, dither=mode)
        assert len(bitmap) == HEIGHT and all(len(row) == WIDTH for row in bitmap)
        assert 0 < _ink_count(bitmap) < WIDTH * HEIGHT


def test_dither_rejects_unknown_mode():
    try:
        process(Image.new("L", (4, 4)), dither="NOISE")
    except ValueError as exc:
        assert "dither" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_bitmap_to_image_upscales_nearest_neighbour():
    bitmap = [[0] * WIDTH for _ in range(HEIGHT)]
    bitmap[0][0] = 1
    image = bitmap_to_image(bitmap, scale=8)
    assert image.size == (WIDTH * 8, HEIGHT * 8)
    assert image.getpixel((0, 0)) == (0, 0, 0)
    assert image.getpixel((7, 7)) == (0, 0, 0)
    assert image.getpixel((8, 0)) == (255, 255, 255)
    assert image.getpixel((0, 8)) == (255, 255, 255)
