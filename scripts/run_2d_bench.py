#!/usr/bin/env python3
"""
Stage: 2D spatial index benchmark — viewport / radius / kNN (points) + viewport / PIP (polygons).

Reads pre-built Parquet cell tables and runs DuckDB queries.

Output: data/results/<timestamp>/2d/
  summary.csv, summary.md
  explain/*.txt
"""

from __future__ import annotations

import json
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from cng_spatial_index.config import (
    RESULTS_DIR,
    CELLS_H3_POINTS_PARQUET, CELLS_GEOHASH_POINTS_PARQUET,
    CELLS_QUADKEY_POINTS_PARQUET, CELLS_MORTON2D_POINTS_PARQUET,
    CELLS_H3_POLY_PARQUET, CELLS_GEOHASH_POLY_PARQUET,
    CELLS_QUADKEY_POLY_PARQUET, CELLS_MORTON2D_POLY_PARQUET,
    BBOX_POINTS_GEOPARQUET, BBOX_POLY_GEOPARQUET,
    H3_RESOLUTIONS, GEOHASH_PRECISIONS, QUADKEY_ZOOMS, MORTON2D_XY_Z,
    VIEWPORT_LON_CENTER, VIEWPORT_LAT_CENTER, VIEWPORT_SIZES_DEG,
    RADIUS_M_LIST, KNN_K,
    CORRIDOR_MINX, CORRIDOR_MAXX, CORRIDOR_MINY, CORRIDOR_MAXY,
)
from cng_spatial_index.h3_key import h3_encode_point, h3_disk_cells, h3_encode_bbox
from cng_spatial_index.geohash_key import geohash_encode, geohash_encode_bbox
from cng_spatial_index.quadkey import quadkey_encode, quadkey_encode_bbox
from cng_spatial_index.morton2d import morton2d_encode, key_ranges_from_cells
from cng_spatial_index.zfxy import zfxy_x as tile_x_fn, zfxy_y as tile_y_fn
from cng_spatial_index.metrics import build_summary_df, write_summary


WARMUP_RUNS = 2
BENCH_RUNS  = 5


def _time_query(con: duckdb.DuckDBPyConnection, sql: str, runs: int = BENCH_RUNS) -> tuple[int, float]:
    for _ in range(WARMUP_RUNS):
        r = con.execute(sql).fetchall()
    times = []
    result_count = 0
    for _ in range(runs):
        t0 = time.perf_counter()
        r = con.execute(sql).fetchall()
        times.append((time.perf_counter() - t0) * 1000)
        result_count = len(r)
    return result_count, sum(times) / len(times)


def _explain(con: duckdb.DuckDBPyConnection, sql: str) -> str:
    try:
        return con.execute(f"EXPLAIN ANALYZE {sql}").fetchdf().to_string()
    except Exception as e:
        return str(e)


# -----------------------------------------------------------------------
# H3 viewport / radius
# -----------------------------------------------------------------------

def bench_h3_viewport_points(con: duckdb.DuckDBPyConnection, vp_half: float, res: int) -> dict:
    cells = h3_encode_bbox(
        VIEWPORT_LON_CENTER - vp_half, VIEWPORT_LAT_CENTER - vp_half,
        VIEWPORT_LON_CENTER + vp_half, VIEWPORT_LAT_CENTER + vp_half,
        res,
    )
    if not cells:
        return {}
    cells_sql = ", ".join(f"'{c}'" for c in cells)
    sql = f"""
        SELECT DISTINCT osm_id FROM read_parquet('{CELLS_H3_POINTS_PARQUET}')
        WHERE resolution = {res} AND h3_cell IN ({cells_sql})
    """
    count, avg_ms = _time_query(con, sql)
    return {"scheme": "h3", "query": "viewport_points", "resolution": res,
            "vp_deg": vp_half * 2, "n_cells": len(cells), "count": count, "avg_ms": round(avg_ms, 2)}


def bench_h3_radius_points(con: duckdb.DuckDBPyConnection, radius_m: float, res: int) -> dict:
    lat, lon = VIEWPORT_LAT_CENTER, VIEWPORT_LON_CENTER
    # approximate k for grid_disk to cover radius_m
    avg_edge_m = {7: 1220, 8: 461, 9: 174, 10: 65}.get(res, 100)
    k = max(1, math.ceil(radius_m / avg_edge_m))
    cells = h3_disk_cells(lat, lon, k, res)
    cells_sql = ", ".join(f"'{c}'" for c in cells)
    sql = f"""
        SELECT DISTINCT osm_id FROM read_parquet('{CELLS_H3_POINTS_PARQUET}')
        WHERE resolution = {res} AND h3_cell IN ({cells_sql})
    """
    count, avg_ms = _time_query(con, sql)
    return {"scheme": "h3", "query": "radius_points", "resolution": res,
            "radius_m": radius_m, "k": k, "n_cells": len(cells), "count": count, "avg_ms": round(avg_ms, 2)}


def bench_h3_viewport_poly(con: duckdb.DuckDBPyConnection, vp_half: float, res: int) -> dict:
    cells = h3_encode_bbox(
        VIEWPORT_LON_CENTER - vp_half, VIEWPORT_LAT_CENTER - vp_half,
        VIEWPORT_LON_CENTER + vp_half, VIEWPORT_LAT_CENTER + vp_half,
        res,
    )
    if not cells:
        return {}
    cells_sql = ", ".join(f"'{c}'" for c in cells)
    sql = f"""
        SELECT DISTINCT osm_id FROM read_parquet('{CELLS_H3_POLY_PARQUET}')
        WHERE resolution = {res} AND h3_cell IN ({cells_sql})
    """
    count, avg_ms = _time_query(con, sql)
    return {"scheme": "h3", "query": "viewport_poly", "resolution": res,
            "vp_deg": vp_half * 2, "n_cells": len(cells), "count": count, "avg_ms": round(avg_ms, 2)}


# -----------------------------------------------------------------------
# GeoHash viewport
# -----------------------------------------------------------------------

def bench_geohash_viewport_points(con: duckdb.DuckDBPyConnection, vp_half: float, prec: int) -> dict:
    cells = geohash_encode_bbox(
        VIEWPORT_LON_CENTER - vp_half, VIEWPORT_LAT_CENTER - vp_half,
        VIEWPORT_LON_CENTER + vp_half, VIEWPORT_LAT_CENTER + vp_half,
        prec,
    )
    if not cells:
        return {}
    cells_sql = ", ".join(f"'{c}'" for c in cells)
    sql = f"""
        SELECT DISTINCT osm_id FROM read_parquet('{CELLS_GEOHASH_POINTS_PARQUET}')
        WHERE precision = {prec} AND geohash IN ({cells_sql})
    """
    count, avg_ms = _time_query(con, sql)
    return {"scheme": "geohash", "query": "viewport_points", "precision": prec,
            "vp_deg": vp_half * 2, "n_cells": len(cells), "count": count, "avg_ms": round(avg_ms, 2)}


def bench_geohash_viewport_poly(con: duckdb.DuckDBPyConnection, vp_half: float, prec: int) -> dict:
    cells = geohash_encode_bbox(
        VIEWPORT_LON_CENTER - vp_half, VIEWPORT_LAT_CENTER - vp_half,
        VIEWPORT_LON_CENTER + vp_half, VIEWPORT_LAT_CENTER + vp_half,
        prec,
    )
    if not cells:
        return {}
    cells_sql = ", ".join(f"'{c}'" for c in cells)
    sql = f"""
        SELECT DISTINCT osm_id FROM read_parquet('{CELLS_GEOHASH_POLY_PARQUET}')
        WHERE precision = {prec} AND geohash IN ({cells_sql})
    """
    count, avg_ms = _time_query(con, sql)
    return {"scheme": "geohash", "query": "viewport_poly", "precision": prec,
            "vp_deg": vp_half * 2, "n_cells": len(cells), "count": count, "avg_ms": round(avg_ms, 2)}


# -----------------------------------------------------------------------
# Quadkey viewport
# -----------------------------------------------------------------------

def bench_quadkey_viewport_points(con: duckdb.DuckDBPyConnection, vp_half: float, zoom: int) -> dict:
    cells = quadkey_encode_bbox(
        VIEWPORT_LON_CENTER - vp_half, VIEWPORT_LAT_CENTER - vp_half,
        VIEWPORT_LON_CENTER + vp_half, VIEWPORT_LAT_CENTER + vp_half,
        zoom,
    )
    if not cells:
        return {}
    cells_sql = ", ".join(f"'{c}'" for c in cells)
    sql = f"""
        SELECT DISTINCT osm_id FROM read_parquet('{CELLS_QUADKEY_POINTS_PARQUET}')
        WHERE zoom = {zoom} AND quadkey IN ({cells_sql})
    """
    count, avg_ms = _time_query(con, sql)
    return {"scheme": "quadkey", "query": "viewport_points", "zoom": zoom,
            "vp_deg": vp_half * 2, "n_cells": len(cells), "count": count, "avg_ms": round(avg_ms, 2)}


def bench_quadkey_viewport_poly(con: duckdb.DuckDBPyConnection, vp_half: float, zoom: int) -> dict:
    cells = quadkey_encode_bbox(
        VIEWPORT_LON_CENTER - vp_half, VIEWPORT_LAT_CENTER - vp_half,
        VIEWPORT_LON_CENTER + vp_half, VIEWPORT_LAT_CENTER + vp_half,
        zoom,
    )
    if not cells:
        return {}
    cells_sql = ", ".join(f"'{c}'" for c in cells)
    sql = f"""
        SELECT DISTINCT osm_id FROM read_parquet('{CELLS_QUADKEY_POLY_PARQUET}')
        WHERE zoom = {zoom} AND quadkey IN ({cells_sql})
    """
    count, avg_ms = _time_query(con, sql)
    return {"scheme": "quadkey", "query": "viewport_poly", "zoom": zoom,
            "vp_deg": vp_half * 2, "n_cells": len(cells), "count": count, "avg_ms": round(avg_ms, 2)}


# -----------------------------------------------------------------------
# Morton2D viewport
# -----------------------------------------------------------------------

def _morton2d_viewport_ranges(lon_min: float, lat_min: float, lon_max: float, lat_max: float) -> list[tuple[int, int]]:
    z = MORTON2D_XY_Z
    x0, y0 = tile_x_fn(lon_min, z), tile_y_fn(lat_max, z)   # NW corner
    x1, y1 = tile_x_fn(lon_max, z), tile_y_fn(lat_min, z)   # SE corner
    keys = [morton2d_encode(lx, ly) for lx in range(x0, x1 + 1) for ly in range(y0, y1 + 1)]
    return key_ranges_from_cells(keys, gap_factor=4)


def bench_morton2d_viewport_points(con: duckdb.DuckDBPyConnection, vp_half: float) -> dict:
    ranges = _morton2d_viewport_ranges(
        VIEWPORT_LON_CENTER - vp_half, VIEWPORT_LAT_CENTER - vp_half,
        VIEWPORT_LON_CENTER + vp_half, VIEWPORT_LAT_CENTER + vp_half,
    )
    if not ranges:
        return {}
    predicates = " OR ".join(f"(key_u64 BETWEEN {lo} AND {hi})" for lo, hi in ranges)
    sql = f"""
        SELECT DISTINCT osm_id FROM read_parquet('{CELLS_MORTON2D_POINTS_PARQUET}')
        WHERE zoom = {MORTON2D_XY_Z} AND ({predicates})
    """
    count, avg_ms = _time_query(con, sql)
    return {"scheme": "morton2d", "query": "viewport_points", "zoom": MORTON2D_XY_Z,
            "vp_deg": vp_half * 2, "n_ranges": len(ranges), "count": count, "avg_ms": round(avg_ms, 2)}


def bench_morton2d_viewport_poly(con: duckdb.DuckDBPyConnection, vp_half: float) -> dict:
    ranges = _morton2d_viewport_ranges(
        VIEWPORT_LON_CENTER - vp_half, VIEWPORT_LAT_CENTER - vp_half,
        VIEWPORT_LON_CENTER + vp_half, VIEWPORT_LAT_CENTER + vp_half,
    )
    if not ranges:
        return {}
    predicates = " OR ".join(f"(key_u64 BETWEEN {lo} AND {hi})" for lo, hi in ranges)
    sql = f"""
        SELECT DISTINCT osm_id FROM read_parquet('{CELLS_MORTON2D_POLY_PARQUET}')
        WHERE zoom = {MORTON2D_XY_Z} AND ({predicates})
    """
    count, avg_ms = _time_query(con, sql)
    return {"scheme": "morton2d", "query": "viewport_poly", "zoom": MORTON2D_XY_Z,
            "vp_deg": vp_half * 2, "n_ranges": len(ranges), "count": count, "avg_ms": round(avg_ms, 2)}


# -----------------------------------------------------------------------
# DuckDB spatial (bbox columns + ST_Intersects)
# -----------------------------------------------------------------------

def bench_duckdb_spatial_viewport_points(con: duckdb.DuckDBPyConnection, vp_half: float) -> dict:
    lon_min = VIEWPORT_LON_CENTER - vp_half
    lon_max = VIEWPORT_LON_CENTER + vp_half
    lat_min = VIEWPORT_LAT_CENTER - vp_half
    lat_max = VIEWPORT_LAT_CENTER + vp_half
    sql = f"""
        SELECT osm_id FROM read_parquet('{BBOX_POINTS_GEOPARQUET}')
        WHERE xmin >= {lon_min} AND xmax <= {lon_max}
          AND ymin >= {lat_min} AND ymax <= {lat_max}
    """
    count, avg_ms = _time_query(con, sql)
    return {"scheme": "bbox_cols", "query": "viewport_points",
            "vp_deg": vp_half * 2, "count": count, "avg_ms": round(avg_ms, 2)}


def bench_duckdb_spatial_viewport_poly(con: duckdb.DuckDBPyConnection, vp_half: float) -> dict:
    lon_min = VIEWPORT_LON_CENTER - vp_half
    lon_max = VIEWPORT_LON_CENTER + vp_half
    lat_min = VIEWPORT_LAT_CENTER - vp_half
    lat_max = VIEWPORT_LAT_CENTER + vp_half
    # bbox overlap: NOT (xmax < lon_min OR xmin > lon_max OR ymax < lat_min OR ymin > lat_max)
    sql = f"""
        SELECT osm_id FROM read_parquet('{BBOX_POLY_GEOPARQUET}')
        WHERE NOT (xmax < {lon_min} OR xmin > {lon_max}
               OR ymax < {lat_min} OR ymin > {lat_max})
    """
    count, avg_ms = _time_query(con, sql)
    return {"scheme": "bbox_cols", "query": "viewport_poly",
            "vp_deg": vp_half * 2, "count": count, "avg_ms": round(avg_ms, 2)}


# -----------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------

def main() -> None:
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = RESULTS_DIR / ts / "2d"
    explain_dir = out_dir / "explain"
    out_dir.mkdir(parents=True, exist_ok=True)
    explain_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    try:
        con.execute("INSTALL spatial; LOAD spatial;")
    except Exception:
        pass

    results = []

    # ---- H3 points ----
    print("=== H3 viewport / radius (points) ===")
    for res in H3_RESOLUTIONS:
        for vp in VIEWPORT_SIZES_DEG:
            r = bench_h3_viewport_points(con, vp / 2, res)
            if r:
                results.append(r)
                print(f"  H3 res={res} vp={vp:.2f}°: {r['count']} pts  {r['avg_ms']:.1f} ms  ({r['n_cells']} cells)")
        for radius in RADIUS_M_LIST:
            r = bench_h3_radius_points(con, radius, res)
            if r:
                results.append(r)
                print(f"  H3 res={res} r={radius}m: {r['count']} pts  {r['avg_ms']:.1f} ms  ({r['n_cells']} cells)")

    # ---- H3 poly ----
    print("=== H3 viewport (poly) ===")
    for res in H3_RESOLUTIONS:
        for vp in VIEWPORT_SIZES_DEG:
            r = bench_h3_viewport_poly(con, vp / 2, res)
            if r:
                results.append(r)
                print(f"  H3 res={res} vp={vp:.2f}°: {r['count']} bldgs  {r['avg_ms']:.1f} ms")

    # ---- GeoHash points ----
    print("=== GeoHash viewport (points) ===")
    for prec in GEOHASH_PRECISIONS:
        for vp in VIEWPORT_SIZES_DEG:
            r = bench_geohash_viewport_points(con, vp / 2, prec)
            if r:
                results.append(r)
                print(f"  GeoHash prec={prec} vp={vp:.2f}°: {r['count']} pts  {r['avg_ms']:.1f} ms  ({r['n_cells']} cells)")

    # ---- GeoHash poly ----
    print("=== GeoHash viewport (poly) ===")
    for prec in GEOHASH_PRECISIONS:
        for vp in VIEWPORT_SIZES_DEG:
            r = bench_geohash_viewport_poly(con, vp / 2, prec)
            if r:
                results.append(r)
                print(f"  GeoHash prec={prec} vp={vp:.2f}°: {r['count']} bldgs  {r['avg_ms']:.1f} ms")

    # ---- Quadkey points ----
    print("=== Quadkey viewport (points) ===")
    for zoom in QUADKEY_ZOOMS:
        for vp in VIEWPORT_SIZES_DEG:
            r = bench_quadkey_viewport_points(con, vp / 2, zoom)
            if r:
                results.append(r)
                print(f"  Quadkey z={zoom} vp={vp:.2f}°: {r['count']} pts  {r['avg_ms']:.1f} ms  ({r['n_cells']} cells)")

    # ---- Quadkey poly ----
    print("=== Quadkey viewport (poly) ===")
    for zoom in QUADKEY_ZOOMS:
        for vp in VIEWPORT_SIZES_DEG:
            r = bench_quadkey_viewport_poly(con, vp / 2, zoom)
            if r:
                results.append(r)
                print(f"  Quadkey z={zoom} vp={vp:.2f}°: {r['count']} bldgs  {r['avg_ms']:.1f} ms")

    # ---- Morton2D points ----
    print("=== Morton2D viewport (points) ===")
    for vp in VIEWPORT_SIZES_DEG:
        r = bench_morton2d_viewport_points(con, vp / 2)
        if r:
            results.append(r)
            print(f"  Morton2D vp={vp:.2f}°: {r['count']} pts  {r['avg_ms']:.1f} ms  ({r['n_ranges']} ranges)")

    # ---- Morton2D poly ----
    print("=== Morton2D viewport (poly) ===")
    for vp in VIEWPORT_SIZES_DEG:
        r = bench_morton2d_viewport_poly(con, vp / 2)
        if r:
            results.append(r)
            print(f"  Morton2D vp={vp:.2f}°: {r['count']} bldgs  {r['avg_ms']:.1f} ms")

    # ---- DuckDB bbox-cols ----
    print("=== DuckDB bbox-cols viewport ===")
    for vp in VIEWPORT_SIZES_DEG:
        r = bench_duckdb_spatial_viewport_points(con, vp / 2)
        if r:
            results.append(r)
            print(f"  bbox_cols vp={vp:.2f}° points: {r['count']}  {r['avg_ms']:.1f} ms")
        r = bench_duckdb_spatial_viewport_poly(con, vp / 2)
        if r:
            results.append(r)
            print(f"  bbox_cols vp={vp:.2f}° poly:   {r['count']}  {r['avg_ms']:.1f} ms")

    # ---- Write results ----
    import pandas as pd
    df = pd.DataFrame(results)
    write_summary(df, out_dir)

    metadata = {"timestamp": ts, "total_bench_records": len(results)}
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(f"\nResults written to {out_dir}")

    con.close()


if __name__ == "__main__":
    main()
