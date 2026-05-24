"""3D Morton / Z-order key.

Bit-interleaves local_x, local_y, hbin into a single uint64 sort key.

IMPORTANT design choices:
- We do NOT interleave raw Web Mercator tile x/y because they are too large
  for safe 64-bit interleaving.
- Instead, we compute local_x = x - x_origin, local_y = y - y_origin relative
  to a reference tile. The origin is the min x/y for the dataset.
- Up to 21 bits per axis → 3*21 = 63 bits ≤ uint64.
- With xy_z=19 and Taito-ku bbox (~600×400 tiles), local_x/y < 2^10 ≈ fine.

For box queries (corridor), the caller must:
  1. Enumerate all (local_x, local_y, hbin) in the corridor.
  2. Compute Morton keys for each.
  3. Sort them to form contiguous or near-contiguous ranges.
  4. Issue DuckDB queries with key_u64 IN (...) or key_u64 BETWEEN ... OR ...
"""

import numpy as np


def _spread_bits(v: int) -> int:
    """Spread a non-negative integer's bits into every 3rd bit position (uint64)."""
    v &= 0x1FFFFF  # 21 bits max
    v = (v | v << 32) & 0x001F00000000FFFF
    v = (v | v << 16) & 0x001F0000FF0000FF
    v = (v | v <<  8) & 0x100F00F00F00F00F
    v = (v | v <<  4) & 0x10C30C30C30C30C3
    v = (v | v <<  2) & 0x1249249249249249
    return v


def morton3d_encode(local_x: int, local_y: int, hbin: int) -> int:
    """Encode (local_x, local_y, hbin) into a uint64 Morton key.

    Each axis is clamped to [0, 2^21 - 1].
    """
    lx = max(0, int(local_x)) & 0x1FFFFF
    ly = max(0, int(local_y)) & 0x1FFFFF
    lb = max(0, int(hbin))    & 0x1FFFFF
    return _spread_bits(lx) | (_spread_bits(ly) << 1) | (_spread_bits(lb) << 2)


def morton3d_encode_vec(
    local_x: "np.ndarray",
    local_y: "np.ndarray",
    hbin: "np.ndarray",
) -> "np.ndarray":
    """Vectorised Morton encoding (uint64)."""
    lx = np.asarray(local_x, dtype=np.int64).clip(0, 0x1FFFFF)
    ly = np.asarray(local_y, dtype=np.int64).clip(0, 0x1FFFFF)
    lb = np.asarray(hbin,    dtype=np.int64).clip(0, 0x1FFFFF)

    def spread(v: np.ndarray) -> np.ndarray:
        v = v.astype(np.int64)
        v = (v | (v << 32)) & np.int64(0x001F00000000FFFF)
        v = (v | (v << 16)) & np.int64(0x001F0000FF0000FF)
        v = (v | (v <<  8)) & np.int64(0x100F00F00F00F00F)
        v = (v | (v <<  4)) & np.int64(0x10C30C30C30C30C3)
        v = (v | (v <<  2)) & np.int64(0x1249249249249249)
        return v.astype(np.uint64)

    return spread(lx) | (spread(ly) << np.uint64(1)) | (spread(lb) << np.uint64(2))


def cell_text(local_x: int, local_y: int, hbin: int) -> str:
    return f"morton3d/{local_x}/{local_y}/{hbin}"


def key_ranges_from_cells(keys: "np.ndarray", gap_factor: int = 2) -> list[tuple[int, int]]:
    """Convert a set of Morton keys into a compact list of (min, max) ranges.

    Merges adjacent keys if the gap is ≤ gap_factor. This reduces the number
    of OR predicates needed for DuckDB row group pruning.
    """
    if len(keys) == 0:
        return []
    s = np.sort(keys.astype(np.int64))
    ranges = []
    lo = int(s[0])
    hi = int(s[0])
    for k in s[1:]:
        k = int(k)
        if k - hi <= gap_factor:
            hi = k
        else:
            ranges.append((lo, hi))
            lo = hi = k
    ranges.append((lo, hi))
    return ranges
