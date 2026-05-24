"""2D Morton (Z-order) key for flat spatial indexing."""

from __future__ import annotations

import numpy as np


def _spread_bits_2d(v: int) -> int:
    """Spread 32-bit integer bits with zeros for 2D interleave."""
    v &= 0x00000000FFFFFFFF
    v = (v | (v << 16)) & 0x0000FFFF0000FFFF
    v = (v | (v <<  8)) & 0x00FF00FF00FF00FF
    v = (v | (v <<  4)) & 0x0F0F0F0F0F0F0F0F
    v = (v | (v <<  2)) & 0x3333333333333333
    v = (v | (v <<  1)) & 0x5555555555555555
    return v


def morton2d_encode(local_x: int, local_y: int) -> int:
    """Interleave local_x and local_y bits into a 64-bit Morton key."""
    return _spread_bits_2d(int(local_x)) | (_spread_bits_2d(int(local_y)) << 1)


def morton2d_encode_vec(local_x: np.ndarray, local_y: np.ndarray) -> np.ndarray:
    lx = local_x.astype(np.int64)
    ly = local_y.astype(np.int64)
    keys = np.zeros(len(lx), dtype=np.int64)
    for i in range(32):
        keys |= ((lx >> i) & 1) << (2 * i)
        keys |= ((ly >> i) & 1) << (2 * i + 1)
    return keys


def key_ranges_from_cells(keys: list[int], gap_factor: int = 2) -> list[tuple[int, int]]:
    """Merge sorted Morton keys into (min, max) ranges for OR predicate."""
    if not keys:
        return []
    sorted_keys = sorted(set(keys))
    ranges: list[tuple[int, int]] = []
    lo = hi = sorted_keys[0]
    for k in sorted_keys[1:]:
        if k - hi <= gap_factor:
            hi = k
        else:
            ranges.append((lo, hi))
            lo = hi = k
    ranges.append((lo, hi))
    return ranges
