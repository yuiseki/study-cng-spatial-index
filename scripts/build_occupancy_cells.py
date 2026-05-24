#!/usr/bin/env python3
"""
Build occupancy cell Parquet files for zfxy, zxy_heightbin, and Morton3D.

Output:
    data/parquet/occupancy_zfxy.parquet
    data/parquet/occupancy_zxy_heightbin.parquet
    data/parquet/occupancy_morton3d.parquet

Each file is sorted by its natural key for Parquet row-group pruning.
"""

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from cng_spatial_index.config import (
    OBSTACLES_GEOPARQUET, PARQUET_DIR,
    OCCUPANCY_ZFXY_PARQUET, OCCUPANCY_ZXY_HEIGHTBIN_PARQUET, OCCUPANCY_MORTON3D_PARQUET,
    ZFXY_Z_LEVELS, XY_Z, VERTICAL_BIN_M_LIST,
    DEFAULT_ROW_GROUP_SIZE,
)
from cng_spatial_index.occupancy import (
    build_occupancy_zfxy,
    build_occupancy_zxy_heightbin,
    build_occupancy_morton3d,
)
from cng_spatial_index.zfxy import zfxy_x_vec, zfxy_y_vec
from cng_spatial_index.zxy_heightbin import zxy_x_vec, zxy_y_vec


def _write_parquet(df: pd.DataFrame, path: Path, sort_cols: list[str], row_group_size: int) -> None:
    df_sorted = df.sort_values(sort_cols)
    table = pa.Table.from_pandas(df_sorted, preserve_index=False)
    pq.write_table(
        table,
        str(path),
        row_group_size=row_group_size,
        compression="snappy",
    )
    size_mb = path.stat().st_size / 1e6
    print(f"    {path.name}  {len(df_sorted):,} rows  {size_mb:.2f} MB  rg_size={row_group_size}")


def main(row_group_size: int = DEFAULT_ROW_GROUP_SIZE) -> None:
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Reading {OBSTACLES_GEOPARQUET}…")
    gdf = gpd.read_parquet(OBSTACLES_GEOPARQUET)
    print(f"  {len(gdf):,} buildings loaded.")

    # ── zfxy ──────────────────────────────────────────────────────────────
    print("\n── zfxy ──")
    frames = []
    for z in ZFXY_Z_LEVELS:
        print(f"  z={z}…")
        df = build_occupancy_zfxy(gdf, z)
        df["zfxy_z"] = z
        frames.append(df)
    zfxy_all = pd.concat(frames, ignore_index=True)
    # Sort: (zfxy_z, f, x, y) for effective row-group pruning on range queries
    _write_parquet(
        zfxy_all, OCCUPANCY_ZFXY_PARQUET,
        sort_cols=["zfxy_z", "f", "x", "y"],
        row_group_size=row_group_size,
    )

    # ── zxy + height_bin ──────────────────────────────────────────────────
    print("\n── zxy_heightbin ──")
    frames = []
    for vbin in VERTICAL_BIN_M_LIST:
        print(f"  vbin={vbin}m…")
        df = build_occupancy_zxy_heightbin(gdf, XY_Z, vbin)
        frames.append(df)
    zxy_all = pd.concat(frames, ignore_index=True)
    # Sort: (xy_z, vertical_bin_m, hbin, x, y)
    _write_parquet(
        zxy_all, OCCUPANCY_ZXY_HEIGHTBIN_PARQUET,
        sort_cols=["xy_z", "vertical_bin_m", "hbin", "x", "y"],
        row_group_size=row_group_size,
    )

    # ── Morton3D ──────────────────────────────────────────────────────────
    print("\n── Morton3D ──")
    # Compute global x/y origin from dataset bbox
    bounds = gdf.geometry.bounds
    lon_min = bounds["minx"].min()
    lat_max = bounds["maxy"].max()
    x_origin = int(zxy_x_vec(lon_min, XY_Z)) - 1
    y_origin = int(zxy_y_vec(lat_max, XY_Z)) - 1
    print(f"  origin: x={x_origin}, y={y_origin}")

    frames = []
    for vbin in VERTICAL_BIN_M_LIST:
        print(f"  vbin={vbin}m…")
        df = build_occupancy_morton3d(gdf, XY_Z, vbin, x_origin, y_origin)
        frames.append(df)
    morton_all = pd.concat(frames, ignore_index=True)

    # Store origin so queries can reconstruct local coordinates
    morton_all["x_origin"] = x_origin
    morton_all["y_origin"] = y_origin

    # Sort by key_u64 for maximum row-group pruning
    _write_parquet(
        morton_all, OCCUPANCY_MORTON3D_PARQUET,
        sort_cols=["xy_z", "vertical_bin_m", "key_u64"],
        row_group_size=row_group_size,
    )

    # Write origin metadata as a small sidecar JSON
    import json
    meta_path = PARQUET_DIR / "morton3d_meta.json"
    meta_path.write_text(json.dumps({
        "xy_z": XY_Z,
        "x_origin": x_origin,
        "y_origin": y_origin,
    }, indent=2))
    print(f"  Morton origin metadata → {meta_path}")

    print("\nDone.")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--row-group-size", type=int, default=DEFAULT_ROW_GROUP_SIZE)
    args = p.parse_args()
    main(args.row_group_size)
