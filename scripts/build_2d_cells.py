#!/usr/bin/env python3
"""
Build 2D cell Parquet tables for all schemes (points and polygons).

Input:
  data/raw/points_taito.geojson          — OSM points
  data/prepared/building_obstacles.geoparquet  — OSM buildings with height model

Output (data/parquet/):
  cells_h3_points.parquet        — osm_id, resolution, h3_cell
  cells_geohash_points.parquet   — osm_id, precision, geohash
  cells_quadkey_points.parquet   — osm_id, zoom, quadkey
  cells_morton2d_points.parquet  — osm_id, zoom, key_u64

  cells_h3_poly.parquet          — osm_id, resolution, h3_cell  (bbox cover)
  cells_geohash_poly.parquet     — osm_id, precision, geohash   (bbox cover)
  cells_quadkey_poly.parquet     — osm_id, zoom, quadkey        (bbox cover)
  cells_morton2d_poly.parquet    — osm_id, zoom, key_u64        (bbox cover)

Also writes flat bbox GeoParquet for DuckDB spatial / RTREE bench:
  data/prepared/points_with_bbox.geoparquet
  data/prepared/poly_with_bbox.geoparquet
"""

from __future__ import annotations

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from cng_spatial_index.config import (
    PARQUET_DIR, PREPARED_DIR,
    POINTS_GEOJSON, OBSTACLES_GEOPARQUET,
    CELLS_H3_POINTS_PARQUET, CELLS_GEOHASH_POINTS_PARQUET,
    CELLS_QUADKEY_POINTS_PARQUET, CELLS_MORTON2D_POINTS_PARQUET,
    CELLS_H3_POLY_PARQUET, CELLS_GEOHASH_POLY_PARQUET,
    CELLS_QUADKEY_POLY_PARQUET, CELLS_MORTON2D_POLY_PARQUET,
    BBOX_POINTS_GEOPARQUET, BBOX_POLY_GEOPARQUET,
    H3_RESOLUTIONS, GEOHASH_PRECISIONS, QUADKEY_ZOOMS, MORTON2D_XY_Z,
    DEFAULT_ROW_GROUP_SIZE,
)
from cng_spatial_index.h3_key import h3_encode_point, h3_encode_bbox
from cng_spatial_index.geohash_key import geohash_encode, geohash_encode_bbox
from cng_spatial_index.quadkey import quadkey_encode, quadkey_encode_bbox
from cng_spatial_index.morton2d import morton2d_encode, key_ranges_from_cells
from cng_spatial_index.zfxy import zfxy_x as tile_x_fn, zfxy_y as tile_y_fn


def _tile_xy(lon: float, lat: float, z: int) -> tuple[int, int]:
    return tile_x_fn(lon, z), tile_y_fn(lat, z)


def _write_parquet(df: pd.DataFrame, path: Path, sort_cols: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = df.sort_values(sort_cols).reset_index(drop=True)
    table = pa.Table.from_pandas(df, preserve_index=False)
    pq.write_table(table, path, row_group_size=DEFAULT_ROW_GROUP_SIZE)
    mb = path.stat().st_size / 1024 / 1024
    print(f"  {path.name}: {len(df):,} rows  {mb:.2f} MB")


# -----------------------------------------------------------------------
# Point helpers
# -----------------------------------------------------------------------

def build_h3_points(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    rows = []
    for res in H3_RESOLUTIONS:
        for _, row in gdf.iterrows():
            lat, lon = row.geometry.y, row.geometry.x
            rows.append({"osm_id": row.osm_id, "resolution": res,
                         "h3_cell": h3_encode_point(lat, lon, res)})
    return pd.DataFrame(rows)


def build_geohash_points(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    rows = []
    for prec in GEOHASH_PRECISIONS:
        for _, row in gdf.iterrows():
            lat, lon = row.geometry.y, row.geometry.x
            rows.append({"osm_id": row.osm_id, "precision": prec,
                         "geohash": geohash_encode(lat, lon, prec)})
    return pd.DataFrame(rows)


def build_quadkey_points(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    rows = []
    for zoom in QUADKEY_ZOOMS:
        for _, row in gdf.iterrows():
            lat, lon = row.geometry.y, row.geometry.x
            rows.append({"osm_id": row.osm_id, "zoom": zoom,
                         "quadkey": quadkey_encode(lat, lon, zoom)})
    return pd.DataFrame(rows)


def build_morton2d_points(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    z = MORTON2D_XY_Z
    rows = []
    for _, row in gdf.iterrows():
        lat, lon = row.geometry.y, row.geometry.x
        lx, ly = _tile_xy(lon, lat, z)
        key = morton2d_encode(lx, ly)
        rows.append({"osm_id": row.osm_id, "zoom": z, "local_x": lx, "local_y": ly,
                     "key_u64": key})
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------
# Polygon (bbox-cover) helpers
# -----------------------------------------------------------------------

def build_h3_poly(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    rows = []
    for res in H3_RESOLUTIONS:
        print(f"  H3 poly res={res}…")
        for _, row in gdf.iterrows():
            b = row.geometry.bounds  # (minx, miny, maxx, maxy)
            cells = h3_encode_bbox(b[0], b[1], b[2], b[3], res)
            for c in cells:
                rows.append({"osm_id": row.osm_id, "resolution": res, "h3_cell": c})
    return pd.DataFrame(rows)


def build_geohash_poly(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    rows = []
    for prec in GEOHASH_PRECISIONS:
        print(f"  GeoHash poly prec={prec}…")
        for _, row in gdf.iterrows():
            b = row.geometry.bounds
            cells = geohash_encode_bbox(b[0], b[1], b[2], b[3], prec)
            for c in cells:
                rows.append({"osm_id": row.osm_id, "precision": prec, "geohash": c})
    return pd.DataFrame(rows)


def build_quadkey_poly(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    rows = []
    for zoom in QUADKEY_ZOOMS:
        print(f"  Quadkey poly zoom={zoom}…")
        for _, row in gdf.iterrows():
            b = row.geometry.bounds
            cells = quadkey_encode_bbox(b[0], b[1], b[2], b[3], zoom)
            for c in cells:
                rows.append({"osm_id": row.osm_id, "zoom": zoom, "quadkey": c})
    return pd.DataFrame(rows)


def build_morton2d_poly(gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    z = MORTON2D_XY_Z
    rows = []
    print(f"  Morton2D poly zoom={z}…")
    for _, row in gdf.iterrows():
        b = row.geometry.bounds
        x0, y0 = _tile_xy(b[0], b[3], z)   # NW corner
        x1, y1 = _tile_xy(b[2], b[1], z)   # SE corner
        for lx in range(x0, x1 + 1):
            for ly in range(y0, y1 + 1):
                key = morton2d_encode(lx, ly)
                rows.append({"osm_id": row.osm_id, "zoom": z, "local_x": lx, "local_y": ly,
                             "key_u64": key})
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------
# Flat bbox GeoParquet for DuckDB spatial / RTREE
# -----------------------------------------------------------------------

def build_bbox_geoparquet(gdf: gpd.GeoDataFrame, path: Path) -> None:
    df = gdf.copy()
    bounds = df.geometry.bounds
    df["xmin"] = bounds["minx"]
    df["ymin"] = bounds["miny"]
    df["xmax"] = bounds["maxx"]
    df["ymax"] = bounds["maxy"]
    df.to_parquet(path)
    mb = path.stat().st_size / 1024 / 1024
    print(f"  {path.name}: {len(df):,} rows  {mb:.2f} MB")


def main() -> None:
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    PREPARED_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading point data…")
    pts = gpd.read_file(POINTS_GEOJSON)
    print(f"  {len(pts):,} points")

    print("Loading polygon (obstacle) data…")
    poly = gpd.read_parquet(OBSTACLES_GEOPARQUET)
    print(f"  {len(poly):,} buildings")

    # --- Points ---
    print("\n=== Point cell tables ===")

    print("Building H3 point cells…")
    df = build_h3_points(pts)
    _write_parquet(df, CELLS_H3_POINTS_PARQUET, ["resolution", "h3_cell"])

    print("Building GeoHash point cells…")
    df = build_geohash_points(pts)
    _write_parquet(df, CELLS_GEOHASH_POINTS_PARQUET, ["precision", "geohash"])

    print("Building Quadkey point cells…")
    df = build_quadkey_points(pts)
    _write_parquet(df, CELLS_QUADKEY_POINTS_PARQUET, ["zoom", "quadkey"])

    print("Building Morton2D point cells…")
    df = build_morton2d_points(pts)
    _write_parquet(df, CELLS_MORTON2D_POINTS_PARQUET, ["zoom", "key_u64"])

    print("\n=== Flat bbox GeoParquet ===")
    build_bbox_geoparquet(pts, BBOX_POINTS_GEOPARQUET)
    build_bbox_geoparquet(poly, BBOX_POLY_GEOPARQUET)

    # --- Polygons ---
    print("\n=== Polygon cell tables (bbox cover) ===")

    print("Building H3 poly cells…")
    df = build_h3_poly(poly)
    _write_parquet(df, CELLS_H3_POLY_PARQUET, ["resolution", "h3_cell"])

    print("Building GeoHash poly cells…")
    df = build_geohash_poly(poly)
    _write_parquet(df, CELLS_GEOHASH_POLY_PARQUET, ["precision", "geohash"])

    print("Building Quadkey poly cells…")
    df = build_quadkey_poly(poly)
    _write_parquet(df, CELLS_QUADKEY_POLY_PARQUET, ["zoom", "quadkey"])

    print("Building Morton2D poly cells…")
    df = build_morton2d_poly(poly)
    _write_parquet(df, CELLS_MORTON2D_POLY_PARQUET, ["zoom", "key_u64"])

    print("\nDone.")


if __name__ == "__main__":
    main()
