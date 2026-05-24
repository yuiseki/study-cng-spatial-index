#!/usr/bin/env python3
"""
Build building_obstacles.geoparquet from the raw buildings GeoJSON.

Applies the height model and adds bbox columns for DuckDB min/max pruning.
No PostGIS dependency.
"""

import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from cng_spatial_index.config import BUILDINGS_GEOJSON, OBSTACLES_GEOPARQUET, PREPARED_DIR
from cng_spatial_index.height_model import estimate_heights


def main() -> None:
    PREPARED_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Reading {BUILDINGS_GEOJSON}…")
    gdf = gpd.read_file(BUILDINGS_GEOJSON)
    print(f"  {len(gdf):,} buildings loaded.")

    # Apply height model
    records = []
    for _, row in gdf.iterrows():
        tags = {
            "height":              row.get("height"),
            "building:levels":     row.get("building_levels"),
            "min_height":          row.get("min_height"),
            "building:min_level":  row.get("building_min_level"),
            "roof:height":         row.get("roof_height"),
            "roof:levels":         row.get("roof_levels"),
        }
        h = estimate_heights(tags)
        records.append({
            "osm_id":       row["osm_id"],
            "max_height_m": h["max_height_m"],
            "min_height_m": h["min_height_m"],
            "height_source": h["height_source"],
            "levels":       h["levels"],
            "min_level":    h["min_level"],
        })

    import pandas as pd
    heights_df = pd.DataFrame(records)
    gdf = gdf.merge(heights_df, on="osm_id", how="left")

    # Add bbox columns (for Parquet min/max pruning without GiST)
    bounds = gdf.geometry.bounds  # xmin, ymin, xmax, ymax
    gdf["xmin"] = bounds["minx"].values
    gdf["ymin"] = bounds["miny"].values
    gdf["xmax"] = bounds["maxx"].values
    gdf["ymax"] = bounds["maxy"].values

    # Height range as z range (for axis-aligned 3D bbox)
    gdf["zmin"] = gdf["min_height_m"]
    gdf["zmax"] = gdf["max_height_m"]

    # Select and reorder columns
    out = gdf[[
        "osm_id", "geometry",
        "xmin", "ymin", "xmax", "ymax",
        "zmin", "zmax",
        "min_height_m", "max_height_m", "height_source",
        "levels", "min_level",
    ]]

    out.to_parquet(OBSTACLES_GEOPARQUET, engine="pyarrow", index=False)

    size_mb = OBSTACLES_GEOPARQUET.stat().st_size / 1e6
    print(f"  Saved → {OBSTACLES_GEOPARQUET}  ({size_mb:.2f} MB)")

    # Quick sanity check
    import duckdb
    con = duckdb.connect()
    stats = con.execute(f"""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE height_source = 'height')                     AS src_height,
            COUNT(*) FILTER (WHERE height_source = 'building:levels_estimated')  AS src_levels,
            COUNT(*) FILTER (WHERE height_source = 'default_15m')                AS src_default,
            MIN(max_height_m)    AS min_h,
            MAX(max_height_m)    AS max_h,
            MEDIAN(max_height_m) AS median_h
        FROM read_parquet('{OBSTACLES_GEOPARQUET}')
    """).fetchdf()
    print(stats.to_string(index=False))
    con.close()


if __name__ == "__main__":
    main()
