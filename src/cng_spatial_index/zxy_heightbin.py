"""zxy + independent height bin cell key.

Unlike zfxy, this scheme separates horizontal resolution (xy_z) from
vertical resolution (vertical_bin_m), so both can be tuned independently.

x = zfxy_x(lon, xy_z)   (same Web Mercator formula)
y = zfxy_y(lat, xy_z)
hbin = floor(height_m / vertical_bin_m)
key  = "{xy_z}/{x}/{y}/{vertical_bin_m}/{hbin}"
"""

import math

import numpy as np

from .zfxy import zfxy_x, zfxy_y, zfxy_x_vec, zfxy_y_vec

# Aliases — same formula, different name to make design intent clear
zxy_x = zfxy_x
zxy_y = zfxy_y
zxy_x_vec = zfxy_x_vec
zxy_y_vec = zfxy_y_vec


def height_bin(height_m: float, vertical_bin_m: float) -> int:
    return int(math.floor(max(0.0, height_m) / vertical_bin_m))


def height_bin_vec(height_m: "np.ndarray | float", vertical_bin_m: float) -> "np.ndarray":
    h = np.maximum(0.0, np.asarray(height_m, dtype=np.float64))
    return np.floor(h / vertical_bin_m).astype(np.int64)


def cell_text(xy_z: int, x: int, y: int, vertical_bin_m: float, hbin: int) -> str:
    return f"{xy_z}/{x}/{y}/{vertical_bin_m}/{hbin}"
