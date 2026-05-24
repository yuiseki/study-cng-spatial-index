"""DuckDB corridor lookup queries for each cell scheme."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import duckdb
import numpy as np

from .zfxy import zfxy_x, zfxy_y, zfxy_f
from .zxy_heightbin import zxy_x, zxy_y, height_bin
from .morton3d import morton3d_encode_vec, key_ranges_from_cells


def _open_db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("INSTALL spatial; LOAD spatial;")
    return con


def query_corridor_zfxy(
    parquet_path: Path,
    corridor_minx: float,
    corridor_miny: float,
    corridor_maxx: float,
    corridor_maxy: float,
    altitude_m: float,
    clearance_m: float,
    z: int,
) -> dict[str, Any]:
    """Query zfxy occupancy parquet for corridor + altitude band."""
    x_min = zfxy_x(corridor_minx, z)
    x_max = zfxy_x(corridor_maxx, z)
    y_min = zfxy_y(corridor_maxy, z)  # lat_max → y_min
    y_max = zfxy_y(corridor_miny, z)  # lat_min → y_max
    f_min = zfxy_f(altitude_m - clearance_m, z)
    f_max = zfxy_f(altitude_m + clearance_m, z)

    sql = f"""
        SELECT COUNT(*) AS candidate_cells, COUNT(DISTINCT osm_id) AS candidate_buildings
        FROM read_parquet('{parquet_path}')
        WHERE x BETWEEN {x_min} AND {x_max}
          AND y BETWEEN {y_min} AND {y_max}
          AND f BETWEEN {f_min} AND {f_max}
    """
    explain_sql = f"""
        EXPLAIN ANALYZE
        SELECT osm_id FROM read_parquet('{parquet_path}')
        WHERE x BETWEEN {x_min} AND {x_max}
          AND y BETWEEN {y_min} AND {y_max}
          AND f BETWEEN {f_min} AND {f_max}
    """

    con = duckdb.connect()
    t0 = time.perf_counter()
    result = con.execute(sql).fetchone()
    elapsed_ms = (time.perf_counter() - t0) * 1000

    explain_text = "\n".join(
        r[0] for r in con.execute(explain_sql).fetchall()
    )
    con.close()

    return {
        "scheme": "zfxy",
        "z": z,
        "vertical_bin_m": None,
        "altitude_m": altitude_m,
        "x_min": x_min, "x_max": x_max,
        "y_min": y_min, "y_max": y_max,
        "f_min": f_min, "f_max": f_max,
        "candidate_cells": result[0],
        "candidate_buildings": result[1],
        "query_time_ms": round(elapsed_ms, 3),
        "sql": sql.strip(),
        "explain": explain_text,
    }


def query_corridor_zxy_heightbin(
    parquet_path: Path,
    corridor_minx: float,
    corridor_miny: float,
    corridor_maxx: float,
    corridor_maxy: float,
    altitude_m: float,
    clearance_m: float,
    xy_z: int,
    vertical_bin_m: float,
) -> dict[str, Any]:
    x_min = zxy_x(corridor_minx, xy_z)
    x_max = zxy_x(corridor_maxx, xy_z)
    y_min = zxy_y(corridor_maxy, xy_z)
    y_max = zxy_y(corridor_miny, xy_z)
    hbin_min = height_bin(altitude_m - clearance_m, vertical_bin_m)
    hbin_max = height_bin(altitude_m + clearance_m, vertical_bin_m)

    sql = f"""
        SELECT COUNT(*) AS candidate_cells, COUNT(DISTINCT osm_id) AS candidate_buildings
        FROM read_parquet('{parquet_path}')
        WHERE xy_z = {xy_z}
          AND vertical_bin_m = {vertical_bin_m}
          AND x BETWEEN {x_min} AND {x_max}
          AND y BETWEEN {y_min} AND {y_max}
          AND hbin BETWEEN {hbin_min} AND {hbin_max}
    """
    explain_sql = f"""
        EXPLAIN ANALYZE
        SELECT osm_id FROM read_parquet('{parquet_path}')
        WHERE xy_z = {xy_z}
          AND vertical_bin_m = {vertical_bin_m}
          AND x BETWEEN {x_min} AND {x_max}
          AND y BETWEEN {y_min} AND {y_max}
          AND hbin BETWEEN {hbin_min} AND {hbin_max}
    """

    con = duckdb.connect()
    t0 = time.perf_counter()
    result = con.execute(sql).fetchone()
    elapsed_ms = (time.perf_counter() - t0) * 1000

    explain_text = "\n".join(r[0] for r in con.execute(explain_sql).fetchall())
    con.close()

    return {
        "scheme": "zxy_heightbin",
        "z": xy_z,
        "vertical_bin_m": vertical_bin_m,
        "altitude_m": altitude_m,
        "x_min": x_min, "x_max": x_max,
        "y_min": y_min, "y_max": y_max,
        "hbin_min": hbin_min, "hbin_max": hbin_max,
        "candidate_cells": result[0],
        "candidate_buildings": result[1],
        "query_time_ms": round(elapsed_ms, 3),
        "sql": sql.strip(),
        "explain": explain_text,
    }


def query_corridor_morton3d(
    parquet_path: Path,
    corridor_minx: float,
    corridor_miny: float,
    corridor_maxx: float,
    corridor_maxy: float,
    altitude_m: float,
    clearance_m: float,
    xy_z: int,
    vertical_bin_m: float,
    x_origin: int,
    y_origin: int,
    gap_factor: int = 4,
) -> dict[str, Any]:
    x_min = zxy_x(corridor_minx, xy_z)
    x_max = zxy_x(corridor_maxx, xy_z)
    y_min = zxy_y(corridor_maxy, xy_z)
    y_max = zxy_y(corridor_miny, xy_z)
    hbin_min = height_bin(altitude_m - clearance_m, vertical_bin_m)
    hbin_max = height_bin(altitude_m + clearance_m, vertical_bin_m)

    # Enumerate all cells, compute Morton keys
    xs = np.arange(x_min, x_max + 1, dtype=np.int64)
    ys = np.arange(y_min, y_max + 1, dtype=np.int64)
    hs = np.arange(hbin_min, hbin_max + 1, dtype=np.int64)

    lxs = xs - x_origin
    lys = ys - y_origin

    # Cartesian product
    gx, gy, gh = np.meshgrid(lxs, lys, hs, indexing="ij")
    all_lx = gx.ravel()
    all_ly = gy.ravel()
    all_h  = gh.ravel()
    keys   = morton3d_encode_vec(all_lx, all_ly, all_h)

    ranges = key_ranges_from_cells(keys, gap_factor=gap_factor)
    n_ranges = len(ranges)

    if n_ranges == 0:
        return {
            "scheme": "morton3d",
            "z": xy_z,
            "vertical_bin_m": vertical_bin_m,
            "altitude_m": altitude_m,
            "candidate_cells": 0,
            "candidate_buildings": 0,
            "query_time_ms": 0.0,
            "n_morton_ranges": 0,
            "sql": "",
            "explain": "",
        }

    # Build WHERE clause with merged ranges
    conditions = " OR ".join(
        f"(key_u64 BETWEEN {lo} AND {hi})" for lo, hi in ranges
    )
    sql = f"""
        SELECT COUNT(*) AS candidate_cells, COUNT(DISTINCT osm_id) AS candidate_buildings
        FROM read_parquet('{parquet_path}')
        WHERE xy_z = {xy_z}
          AND vertical_bin_m = {vertical_bin_m}
          AND ({conditions})
    """
    explain_sql = f"""
        EXPLAIN ANALYZE
        SELECT osm_id FROM read_parquet('{parquet_path}')
        WHERE xy_z = {xy_z}
          AND vertical_bin_m = {vertical_bin_m}
          AND ({conditions})
    """

    con = duckdb.connect()
    t0 = time.perf_counter()
    result = con.execute(sql).fetchone()
    elapsed_ms = (time.perf_counter() - t0) * 1000

    explain_text = "\n".join(r[0] for r in con.execute(explain_sql).fetchall())
    con.close()

    return {
        "scheme": "morton3d",
        "z": xy_z,
        "vertical_bin_m": vertical_bin_m,
        "altitude_m": altitude_m,
        "x_min": x_min, "x_max": x_max,
        "y_min": y_min, "y_max": y_max,
        "hbin_min": hbin_min, "hbin_max": hbin_max,
        "n_morton_ranges": n_ranges,
        "candidate_cells": result[0],
        "candidate_buildings": result[1],
        "query_time_ms": round(elapsed_ms, 3),
        "sql": sql.strip(),
        "explain": explain_text,
    }
