"""zfxy cell key functions.

f = floor(2^z * h / 2^25)
x = floor(2^z * (lon + 180) / 360)
y = floor(2^z * (1 - ln(tan(lat_rad) + 1/cos(lat_rad)) / pi) / 2)

Vertical granularity (metres per f-unit):
    z=17: 256 m   z=19: 64 m   z=21: 16 m   z=22: 8 m
"""

import math
from typing import Sequence

import numpy as np

_Z_HEIGHT = 25  # 2^25 = 33,554,432 m (zfxy height constant)


def zfxy_x(lon: float, z: int) -> int:
    return int(math.floor(2**z * ((lon + 180.0) / 360.0)))


def zfxy_y(lat: float, z: int) -> int:
    lat_rad = math.radians(lat)
    n = 2**z
    return int(math.floor(n * (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0))


def zfxy_f(height_m: float, z: int) -> int:
    return int(math.floor(2**z * max(0.0, height_m) / 2**_Z_HEIGHT))


def zfxy_cell_text(z: int, f: int, x: int, y: int) -> str:
    return f"{z}/{f}/{x}/{y}"


def zfxy_metres_per_f(z: int) -> float:
    """Return the height granularity (metres per f-unit) at zoom level z."""
    return 2**_Z_HEIGHT / 2**z


# ── Vectorised versions for Pandas / NumPy ──────────────────────────────────

def zfxy_x_vec(lon: "np.ndarray | float", z: int) -> "np.ndarray":
    return np.floor(2**z * ((lon + 180.0) / 360.0)).astype(np.int64)


def zfxy_y_vec(lat: "np.ndarray | float", z: int) -> "np.ndarray":
    lat_rad = np.radians(lat)
    n = 2**z
    return np.floor(
        n * (1.0 - np.log(np.tan(lat_rad) + 1.0 / np.cos(lat_rad)) / np.pi) / 2.0
    ).astype(np.int64)


def zfxy_f_vec(height_m: "np.ndarray | float", z: int) -> "np.ndarray":
    h = np.maximum(0.0, np.asarray(height_m, dtype=np.float64))
    return np.floor(2**z * h / 2**_Z_HEIGHT).astype(np.int64)
