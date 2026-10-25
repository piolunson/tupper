"""Generate the .ico and combo arrow. Run: python assets/make_icon.py"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ACCENT = (255, 106, 0, 255)
WHITE = (242, 242, 242, 255)
BLACK = (5, 5, 5, 255)

T_MATRIX = [
    "#########",
    "#########",
    "#########",
    "...###...",
    "...###...",
    "...###...",
    "...###...",
    "...###...",
    "...###...",
]


def build_icon(size: int = 256) -> Image.Image:
    image = Image.new("RGBA", (size, size), BLACK)
    draw = ImageDraw.Draw(image)
    border = max(2, size // 18)
    draw.rectangle((0, 0, size - 1, size - 1), outline=ACCENT, width=border)
    draw.rectangle(
        (border + 2, border + 2, size - border - 3, size - border - 3),
        outline=BLACK,
        width=max(1, size // 64),
    )

    cells = len(T_MATRIX)
    gap = max(1, size // 64)
    inner = size - 2 * (border + size // 10)
    cell = inner // cells
    origin = (size - cell * cells) // 2
    for row, line in enumerate(T_MATRIX):
        for col, ch in enumerate(line):
            if ch != "#":
                continue
            x0 = origin + col * cell
            y0 = origin + row * cell
            draw.rectangle(
                (x0 + gap, y0 + gap, x0 + cell - gap - 1, y0 + cell - gap - 1),
                fill=WHITE,
            )

    # accent registration tick, technical-sheet flavour
    tick = max(2, size // 32)
    draw.line((size // 3, size - border - size // 12, 2 * size // 3, size - border - size // 12), fill=ACCENT, width=tick)
    return image


def build_arrow() -> Image.Image:
    image = Image.new("RGBA", (9, 6), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.polygon([(0, 0), (8, 0), (4, 5)], fill=ACCENT)
    return image


def main():
    (HERE / "ui").mkdir(exist_ok=True)
    icon = build_icon(256)
    icon.save(HERE / "tupper.png")
    icon.save(
        HERE / "tupper.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    build_arrow().save(HERE / "ui" / "arrow.png")
    print("wrote", HERE / "tupper.ico", "and ui/arrow.png")


if __name__ == "__main__":
    main()
