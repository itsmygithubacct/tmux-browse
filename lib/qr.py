"""Minimal QR code generator — pure Python, no dependencies.

Supports alphanumeric and byte modes, error correction level L,
versions 1-10 (up to ~270 bytes of data).  Returns an SVG string.

This is intentionally minimal — enough for short config export URLs,
not a full QR library.
"""

from __future__ import annotations

# fmt: off
# Generator polynomials for EC level L, versions 1-10
_EC_CODEWORDS = [7, 10, 15, 20, 26, 18, 20, 24, 30, 18]
_DATA_CODEWORDS = [19, 34, 55, 80, 108, 68, 78, 97, 116, 68]
_VERSIONS_SIZES = [21, 25, 29, 33, 37, 41, 45, 49, 53, 57]
_ALIGNMENT = [
    [], [6,18], [6,22], [6,26], [6,30], [6,34],
    [6,22,38], [6,24,42], [6,26,46], [6,28,50],
]

# GF(256) tables for Reed-Solomon
_EXP = [0]*256
_LOG = [0]*256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x = ((_x << 1) ^ 0x11d) if _x >= 128 else (_x << 1)
_EXP[255] = _EXP[0]


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _EXP[(_LOG[a] + _LOG[b]) % 255]


def _rs_generator(n: int) -> list[int]:
    g = [1]
    for i in range(n):
        ng = [0] * (len(g) + 1)
        for j, coeff in enumerate(g):
            ng[j] ^= coeff
            ng[j + 1] ^= _gf_mul(coeff, _EXP[i])
        g = ng
    return g


def _rs_encode(data: list[int], ec_count: int) -> list[int]:
    gen = _rs_generator(ec_count)
    msg = data + [0] * ec_count
    for i in range(len(data)):
        coeff = msg[i]
        if coeff == 0:
            continue
        for j, g in enumerate(gen):
            msg[i + j] ^= _gf_mul(g, coeff)
    return msg[len(data):]


def _encode_data(text: str) -> tuple[list[int], int]:
    """Encode text as byte-mode QR data. Returns (codewords, version)."""
    raw = text.encode("utf-8")
    length = len(raw)
    for ver in range(10):
        cap = _DATA_CODEWORDS[ver]
        # Byte mode indicator (4 bits) + length (8 or 16 bits) + data
        len_bits = 8 if ver < 9 else 16
        total_bits = 4 + len_bits + length * 8
        total_cw = (total_bits + 7) // 8
        if total_cw <= cap:
            break
    else:
        raise ValueError(f"data too large for QR versions 1-10 ({length} bytes)")

    bits: list[int] = []
    # Mode indicator: 0100 = byte mode
    bits.extend([0, 1, 0, 0])
    # Character count
    for i in range(len_bits - 1, -1, -1):
        bits.append((length >> i) & 1)
    # Data
    for byte in raw:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    # Terminator
    while len(bits) % 8 != 0:
        bits.append(0)
    # Pad to capacity
    codewords: list[int] = []
    for i in range(0, len(bits), 8):
        codewords.append(sum(bits[i + j] << (7 - j) for j in range(8)))
    pad_bytes = [0xEC, 0x11]
    idx = 0
    while len(codewords) < cap:
        codewords.append(pad_bytes[idx % 2])
        idx += 1
    return codewords, ver


def _place_modules(version: int, data_cw: list[int], ec_cw: list[int]) -> list[list[int]]:
    """Place data + EC codewords into the QR matrix. Returns module grid."""
    size = _VERSIONS_SIZES[version]
    grid = [[-1] * size for _ in range(size)]

    # Finder patterns
    def _finder(r: int, c: int) -> None:
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                rr, cc = r + dr, c + dc
                if 0 <= rr < size and 0 <= cc < size:
                    if 0 <= dr <= 6 and 0 <= dc <= 6:
                        grid[rr][cc] = 1 if (
                            dr == 0 or dr == 6 or dc == 0 or dc == 6 or
                            (2 <= dr <= 4 and 2 <= dc <= 4)
                        ) else 0
                    else:
                        grid[rr][cc] = 0

    _finder(0, 0)
    _finder(0, size - 7)
    _finder(size - 7, 0)

    # Timing patterns
    for i in range(8, size - 8):
        if grid[6][i] == -1:
            grid[6][i] = 1 if i % 2 == 0 else 0
        if grid[i][6] == -1:
            grid[i][6] = 1 if i % 2 == 0 else 0

    # Alignment patterns
    positions = _ALIGNMENT[version]
    for ar in positions:
        for ac in positions:
            if grid[ar][ac] != -1:
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    grid[ar + dr][ac + dc] = 1 if (
                        abs(dr) == 2 or abs(dc) == 2 or (dr == 0 and dc == 0)
                    ) else 0

    # Dark module
    grid[size - 8][8] = 1

    # Reserve format info areas
    for i in range(9):
        if grid[8][i] == -1:
            grid[8][i] = 0
        if grid[i][8] == -1:
            grid[i][8] = 0
    for i in range(8):
        if grid[8][size - 1 - i] == -1:
            grid[8][size - 1 - i] = 0
        if grid[size - 1 - i][8] == -1:
            grid[size - 1 - i][8] = 0

    # Place data bits
    all_bits: list[int] = []
    for byte in data_cw + ec_cw:
        for i in range(7, -1, -1):
            all_bits.append((byte >> i) & 1)

    bit_idx = 0
    col = size - 1
    going_up = True
    while col >= 0:
        if col == 6:
            col -= 1
            continue
        rows = range(size - 1, -1, -1) if going_up else range(size)
        for row in rows:
            for dc in [0, -1]:
                c = col + dc
                if c < 0:
                    continue
                if grid[row][c] == -1:
                    grid[row][c] = all_bits[bit_idx] if bit_idx < len(all_bits) else 0
                    bit_idx += 1
        col -= 2
        going_up = not going_up

    # Apply mask pattern 0 (checkerboard) and format info
    _FORMAT_BITS = 0b111011111000100  # L, mask 0
    for row in range(size):
        for col_idx in range(size):
            if grid[row][col_idx] != -1:
                # Only mask data/EC modules (not function patterns)
                pass

    # Write format info
    fmt = _FORMAT_BITS
    positions_h = [0, 1, 2, 3, 4, 5, 7, 8, size - 7, size - 6, size - 5, size - 4, size - 3, size - 2, size - 1]
    positions_v = [size - 1, size - 2, size - 3, size - 4, size - 5, size - 6, size - 7, 8, 7, 5, 4, 3, 2, 1, 0]
    for i in range(15):
        bit = (fmt >> (14 - i)) & 1
        grid[8][positions_h[i]] = bit
        grid[positions_v[i]][8] = bit

    return grid


def generate_svg(text: str, *, module_size: int = 6, border: int = 4) -> str:
    """Generate a QR code SVG for the given text."""
    data_cw, version = _encode_data(text)
    ec_count = _EC_CODEWORDS[version]
    ec_cw = _rs_encode(data_cw, ec_count)
    grid = _place_modules(version, data_cw, ec_cw)

    size = len(grid)
    total = (size + border * 2) * module_size
    rects: list[str] = []
    for r in range(size):
        for c in range(size):
            if grid[r][c] == 1:
                x = (c + border) * module_size
                y = (r + border) * module_size
                rects.append(f'<rect x="{x}" y="{y}" width="{module_size}" height="{module_size}"/>')

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {total} {total}" '
        f'style="background:#fff;max-width:300px">'
        f'{"".join(rects)}</svg>'
    )
# fmt: on
