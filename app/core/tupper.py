"""Tupper's self-referential formula -- exact integer core.

The formula (Jeff Tupper, 2001):

    1/2 < floor( mod( floor(y/17) * 2^( -17*floor(x) - mod(floor(y),17) ), 2 ) )

For every integer cell (floor(x), floor(y)) the expression is either 0 or 1, so
the plotted set is a union of 1x1 cells.  Writing N = floor(y/17) and
r = mod(floor(y), 17), the cell is black iff bit number 17*i + r of N is set,
where i = floor(x).  This module exploits that identity while evaluating the
same integers the formula uses -- no prebaked bitmaps are involved.

Orientation
-----------
The formula's own portrait, plotted in the true (x right, y up) plane, is
rotated 180 degrees.  Every renderer that shows it as readable text reverses
both axes (Wikipedia notes the same about its plot).  This module therefore
works in "display orientation": 17 rows (top to bottom) by 106 columns (left to
right), where display column ``c`` is formula column ``105 - c`` and display
row ``r`` is the formula's ``mod(floor(y), 17)`` offset.  That is exactly the
reversed-axes plot: x = 0 at the right edge, y = k at the top edge.
"""

from __future__ import annotations

import math
from fractions import Fraction

WIDTH = 106
HEIGHT = 17
CELL_COUNT = WIDTH * HEIGHT

#: The 543-digit constant published with the formula.  It encodes the formula's
#: own portrait.
ORIGINAL_K = int(
    "96093937991895888497167296212785275471500433966012930665150551927170280"
    "23952664246896428421743507181212671537827706233559932372808741443078913"
    "25963941337723487857735749823926629715517173716995165232890538221612403"
    "23885586618401323558513604882869333790249145422928866708109618449609170"
    "51834540678277315517054053816273809676025656250169814820834187831638491"
    "15590225610003652351370343874461848378737238198224849863465033159410054"
    "97470059313833922649724946175154572836670236974546101465599793379853748"
    "3143786841806593422227898388722980000748404719"
)

Bitmap = list[list[int]]


# --------------------------------------------------------------------------
# bit-level primitives
# --------------------------------------------------------------------------

def cell_is_black(n: int, col: int, row: int) -> int:
    """Return 1 when display cell (col, row) of bitmap ``n`` is black.

    ``n`` is floor(y/17) for the band being displayed.  Display column ``col``
    corresponds to formula x-offset ``105 - col`` (axes reversed), and ``row``
    is the offset inside the 17-row band.
    """
    if n <= 0 or not (0 <= col < WIDTH) or not (0 <= row < HEIGHT):
        return 0
    bit = 17 * (WIDTH - 1 - col) + row
    return (n >> bit) & 1


def formula_holds(x, y, k: int) -> bool:
    """Evaluate the published inequality literally, with exact arithmetic.

    ``x`` and ``y`` may be ints or Fractions.  This is deliberately the slow,
    literal transcription of the formula; it exists so the fast cell/bit path
    above can be checked against the real thing in the tests.
    """
    fx = math.floor(x)
    fy = math.floor(y)
    q = math.floor(Fraction(y) / 17)
    exponent = 17 * fx + (fy % 17)
    if exponent >= 0:
        scaled = Fraction(q, 2**exponent)
    else:
        scaled = Fraction(q * 2 ** (-exponent), 1)
    inner = scaled % 2
    return Fraction(1, 2) < Fraction(math.floor(inner), 1)


# --------------------------------------------------------------------------
# bitmap <-> k
# --------------------------------------------------------------------------

def empty_bitmap() -> Bitmap:
    return [[0] * WIDTH for _ in range(HEIGHT)]


def full_bitmap() -> Bitmap:
    return [[1] * WIDTH for _ in range(HEIGHT)]


def bitmap_from_rows(rows: list[str], on: str = "#") -> Bitmap:
    """Build a bitmap from 17 strings of 106 characters ('#' = black)."""
    if len(rows) != HEIGHT:
        raise ValueError(f"expected {HEIGHT} rows, got {len(rows)}")
    out: Bitmap = []
    for index, line in enumerate(rows):
        line = line.strip("\n")
        if len(line) != WIDTH:
            raise ValueError(
                f"row {index} has {len(line)} columns, expected {WIDTH}"
            )
        out.append([1 if ch == on else 0 for ch in line])
    return out


def rows_from_bitmap(bitmap: Bitmap, on: str = "#", off: str = ".") -> list[str]:
    return ["".join(on if cell else off for cell in row) for row in bitmap]


def encode(bitmap: Bitmap) -> int:
    """Encode a display-orientation bitmap as Tupper's k = 17 * N.

    Bit index inside N is ``17 * x + y`` with x = 105 - col (rightmost display
    column is the least significant one) and y = row.
    """
    if len(bitmap) != HEIGHT or any(len(row) != WIDTH for row in bitmap):
        raise ValueError(f"bitmap must be {HEIGHT} rows of {WIDTH} cells")
    n = 0
    for row in range(HEIGHT):
        for col in range(WIDTH):
            if bitmap[row][col]:
                n |= 1 << (17 * (WIDTH - 1 - col) + row)
    return 17 * n


def decode(k: int) -> Bitmap:
    """Decode k into a display-orientation 17x106 bitmap."""
    if k < 0:
        raise ValueError("k must be non-negative")
    n = k // 17
    return decode_n(n)


def decode_n(n: int) -> Bitmap:
    """Decode a raw band number N (k = 17N) as a bitmap."""
    if n <= 0:
        return empty_bitmap()
    return [
        [cell_is_black(n, col, row) for col in range(WIDTH)]
        for row in range(HEIGHT)
    ]


def parse_k(text: str) -> int:
    cleaned = "".join(ch for ch in text if ch.isdigit())
    if not cleaned:
        raise ValueError("no digits found")
    return int(cleaned)


def format_k(k: int) -> str:
    return str(k)


def validate_k(k: int) -> tuple[bool, str]:
    """Return (valid, note) for a decoded constant."""
    if k < 0:
        return False, "K MUST BE >= 0"
    if k % 17:
        return True, f"K NOT A MULTIPLE OF 17 // N = FLOOR(K/17) = {k // 17}"
    return True, f"N = K/17 -> {len(str(k // 17))} DIGIT BAND INDEX"


# --------------------------------------------------------------------------
# graph sampling (shared by UI and tests)
# --------------------------------------------------------------------------

def plot_tile(
    k: int,
    u0: float,
    v0: float,
    scale: float,
    width: int,
    height: int,
    samples: int = 1,
    scale_y: float | None = None,
) -> bytearray:
    """Rasterise a slice of the (x, y) plane for the given k.

    World coordinates are display units: ``u`` is the display column (0..106,
    increasing right) and ``v`` is the display row measured from ``y = k``
    (increasing downward).  Screen pixel (px, py) maps to world
    (u0 + px/scale, v0 + py/scale_y).

    Returns ``width * height`` bytes, 1 = black (formula true), 0 = white.
    When both scales are >= 1 whole cells are filled exactly; below one pixel
    per cell every pixel is point-sampled (optionally supersampled) through the
    same big-integer formula.  ``scale_y`` defaults to ``scale``.
    """
    sy = scale if scale_y is None else scale_y
    if scale <= 0 or sy <= 0:
        raise ValueError("scale must be positive")
    width = int(width)
    height = int(height)
    if width <= 0 or height <= 0:
        return bytearray()
    if k < 0:
        raise ValueError("k must be non-negative")

    n_ref = k // 17
    buf = bytearray(width * height)

    if scale >= 1.0 and sy >= 1.0:
        col_start = math.floor(u0)
        col_end = math.ceil(u0 + width / scale)
        step_start = math.floor(v0)
        step_end = math.ceil(v0 + height / sy)
        for step in range(step_start, step_end):
            d, row = divmod(step, 17)
            n = n_ref + d
            y0 = max(0, math.ceil((step - v0) * sy - 1e-9))
            y1 = min(height, math.ceil((step + 1 - v0) * sy - 1e-9))
            if y1 <= y0 or n <= 0:
                continue
            for col in range(max(0, col_start), min(WIDTH, col_end)):
                if not cell_is_black(n, col, row):
                    continue
                x0 = max(0, math.ceil((col - u0) * scale - 1e-9))
                x1 = min(width, math.ceil((col + 1 - u0) * scale - 1e-9))
                if x1 <= x0:
                    continue
                span = b"\x01" * (x1 - x0)
                for yy in range(y0, y1):
                    base = yy * width
                    buf[base + x0 : base + x1] = span
        return buf

    # Sub-cell zoom: sample the formula per pixel.
    inv_x = 1.0 / scale
    inv_y = 1.0 / sy
    taps = max(1, int(samples))
    offsets_x = [(i + 0.5) / taps * inv_x for i in range(taps)]
    offsets_y = [(i + 0.5) / taps * inv_y for i in range(taps)]
    inv_taps = 1.0 / (taps * taps)
    for py in range(height):
        row_base = py * width
        for px in range(width):
            hits = 0
            for oy in offsets_y:
                v = v0 + py * inv_y + oy
                step = math.floor(v)
                d, row = divmod(step, 17)
                n = n_ref + d
                if n <= 0:
                    continue
                for ox in offsets_x:
                    u = u0 + px * inv_x + ox
                    col = math.floor(u)
                    if 0 <= col < WIDTH and cell_is_black(n, col, row):
                        hits += 1
            if hits * inv_taps >= 0.5:
                buf[row_base + px] = 1
    return buf
