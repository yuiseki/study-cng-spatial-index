"""Build occupancy cell tables from building obstacle GeoDataFrame.

One row per (osm_id, cell) mapping. Buildings expand into a set of cells
that cover their footprint (x/y bbox cover) and height range (f / hbin cover).

Safety caps prevent runaway expansion for large buildings.
"""

from __future__ import annotations

import logging
from typing import Iterator

import numpy as np
import pandas as pd

from .config import XY_CAP, FXY_CAP
from .zfxy import zfxy_x_vec, zfxy_y_vec, zfxy_f_vec, zfxy_cell_text
from .zxy_heightbin import zxy_x_vec, zxy_y_vec, height_bin_vec, cell_text as zxy_cell_text
from .morton3d import morton3d_encode_vec, cell_text as morton_cell_text, key_ranges_from_cells

logger = logging.getLogger(__name__)


# ── helpers ──────────────────────────────────────────────────────────────────

def _xy_range(geom, z: int) -> tuple[int, int, int, int] | None:
    """Return (x_min, x_max, y_min, y_max) for a geometry bbox at zoom z.

    y_min ≤ y_max after correcting the tile-y inversion.
    """
    from shapely.geometry import box
    b = geom.bounds  # (minx, miny, maxx, maxy)
    x_min = int(zfxy_x_vec(b[0], z))
    x_max = int(zfxy_x_vec(b[2], z))
    y_min = int(zfxy_y_vec(b[3], z))  # lat_max → y_min (tile y is north-down)
    y_max = int(zfxy_y_vec(b[1], z))  # lat_min → y_max
    if x_min > x_max:
        x_min, x_max = x_max, x_min
    if y_min > y_max:
        y_min, y_max = y_max, y_min
    return x_min, x_max, y_min, y_max


# ── zfxy cells ────────────────────────────────────────────────────────────────

def building_cells_zfxy(
    row: pd.Series,
    z: int,
    xy_cap: int = XY_CAP,
    fxy_cap: int = FXY_CAP,
) -> list[dict] | None:
    """Expand a single building row into zfxy cells. Returns None if capped."""
    geom = row.geometry
    if geom is None or geom.is_empty:
        return None

    xy = _xy_range(geom, z)
    if xy is None:
        return None
    x_min, x_max, y_min, y_max = xy

    f_min = int(zfxy_f_vec(row.min_height_m, z))
    f_max = int(zfxy_f_vec(row.max_height_m, z))

    xy_count = (x_max - x_min + 1) * (y_max - y_min + 1)
    f_count  = f_max - f_min + 1
    total    = xy_count * f_count

    if xy_count > xy_cap or total > fxy_cap:
        return None

    cells = []
    for f in range(f_min, f_max + 1):
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                cells.append({
                    "osm_id":    row.osm_id,
                    "scheme":    "zfxy",
                    "xy_z":      z,
                    "zfxy_z":    z,
                    "vertical_bin_m": None,
                    "x":         x,
                    "y":         y,
                    "f":         f,
                    "hbin":      None,
                    "key_text":  zfxy_cell_text(z, f, x, y),
                    "key_u64":   None,
                    "blocked":   True,
                })
    return cells


# ── zxy + height_bin cells ────────────────────────────────────────────────────

def building_cells_zxy_heightbin(
    row: pd.Series,
    xy_z: int,
    vertical_bin_m: float,
    xy_cap: int = XY_CAP,
    fxy_cap: int = FXY_CAP,
) -> list[dict] | None:
    geom = row.geometry
    if geom is None or geom.is_empty:
        return None

    xy = _xy_range(geom, xy_z)
    if xy is None:
        return None
    x_min, x_max, y_min, y_max = xy

    hbin_min = int(height_bin_vec(row.min_height_m, vertical_bin_m))
    hbin_max = int(height_bin_vec(row.max_height_m, vertical_bin_m))

    xy_count   = (x_max - x_min + 1) * (y_max - y_min + 1)
    hbin_count = hbin_max - hbin_min + 1
    total      = xy_count * hbin_count

    if xy_count > xy_cap or total > fxy_cap:
        return None

    cells = []
    for hbin in range(hbin_min, hbin_max + 1):
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                cells.append({
                    "osm_id":    row.osm_id,
                    "scheme":    "zxy_heightbin",
                    "xy_z":      xy_z,
                    "zfxy_z":    None,
                    "vertical_bin_m": vertical_bin_m,
                    "x":         x,
                    "y":         y,
                    "f":         None,
                    "hbin":      hbin,
                    "key_text":  zxy_cell_text(xy_z, x, y, vertical_bin_m, hbin),
                    "key_u64":   None,
                    "blocked":   True,
                })
    return cells


# ── Morton3D cells ────────────────────────────────────────────────────────────

def building_cells_morton3d(
    row: pd.Series,
    xy_z: int,
    vertical_bin_m: float,
    x_origin: int,
    y_origin: int,
    xy_cap: int = XY_CAP,
    fxy_cap: int = FXY_CAP,
) -> list[dict] | None:
    geom = row.geometry
    if geom is None or geom.is_empty:
        return None

    xy = _xy_range(geom, xy_z)
    if xy is None:
        return None
    x_min, x_max, y_min, y_max = xy

    hbin_min = int(height_bin_vec(row.min_height_m, vertical_bin_m))
    hbin_max = int(height_bin_vec(row.max_height_m, vertical_bin_m))

    xy_count   = (x_max - x_min + 1) * (y_max - y_min + 1)
    hbin_count = hbin_max - hbin_min + 1
    total      = xy_count * hbin_count

    if xy_count > xy_cap or total > fxy_cap:
        return None

    cells = []
    for hbin in range(hbin_min, hbin_max + 1):
        for x in range(x_min, x_max + 1):
            for y in range(y_min, y_max + 1):
                lx = x - x_origin
                ly = y - y_origin
                key = int(morton3d_encode_vec(
                    np.array([lx]), np.array([ly]), np.array([hbin])
                )[0])
                cells.append({
                    "osm_id":    row.osm_id,
                    "scheme":    "morton3d",
                    "xy_z":      xy_z,
                    "zfxy_z":    None,
                    "vertical_bin_m": vertical_bin_m,
                    "x":         x,
                    "y":         y,
                    "f":         None,
                    "hbin":      hbin,
                    "key_text":  morton_cell_text(lx, ly, hbin),
                    "key_u64":   key,
                    "blocked":   True,
                })
    return cells


# ── batch builders ────────────────────────────────────────────────────────────

def build_occupancy_zfxy(
    gdf: "geopandas.GeoDataFrame",
    z: int,
    xy_cap: int = XY_CAP,
    fxy_cap: int = FXY_CAP,
) -> pd.DataFrame:
    rows = []
    skipped = 0
    for _, row in gdf.iterrows():
        cells = building_cells_zfxy(row, z, xy_cap, fxy_cap)
        if cells is None:
            skipped += 1
        else:
            rows.extend(cells)
    if skipped:
        logger.info("zfxy z=%d: %d buildings skipped (cap exceeded)", z, skipped)
    return pd.DataFrame(rows)


def build_occupancy_zxy_heightbin(
    gdf: "geopandas.GeoDataFrame",
    xy_z: int,
    vertical_bin_m: float,
    xy_cap: int = XY_CAP,
    fxy_cap: int = FXY_CAP,
) -> pd.DataFrame:
    rows = []
    skipped = 0
    for _, row in gdf.iterrows():
        cells = building_cells_zxy_heightbin(row, xy_z, vertical_bin_m, xy_cap, fxy_cap)
        if cells is None:
            skipped += 1
        else:
            rows.extend(cells)
    if skipped:
        logger.info("zxy_heightbin xy_z=%d vbin=%s: %d buildings skipped", xy_z, vertical_bin_m, skipped)
    return pd.DataFrame(rows)


def build_occupancy_morton3d(
    gdf: "geopandas.GeoDataFrame",
    xy_z: int,
    vertical_bin_m: float,
    x_origin: int,
    y_origin: int,
    xy_cap: int = XY_CAP,
    fxy_cap: int = FXY_CAP,
) -> pd.DataFrame:
    rows = []
    skipped = 0
    for _, row in gdf.iterrows():
        cells = building_cells_morton3d(row, xy_z, vertical_bin_m, x_origin, y_origin, xy_cap, fxy_cap)
        if cells is None:
            skipped += 1
        else:
            rows.extend(cells)
    if skipped:
        logger.info("morton3d xy_z=%d vbin=%s: %d buildings skipped", xy_z, vertical_bin_m, skipped)
    return pd.DataFrame(rows)
