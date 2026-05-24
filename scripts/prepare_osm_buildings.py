#!/usr/bin/env python3
"""
Export OSM Taito-ku buildings from PostgreSQL to GeoJSON.

Reads from the study-pg-spatial-index zfxy container (localhost:55442).
Output: data/raw/buildings_taito.geojson

This is the ONLY script that requires PostgreSQL access.
All subsequent steps read from the GeoJSON and are PostGIS-independent.
"""

import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from cng_spatial_index.config import (
    PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD,
    RAW_DIR, BUILDINGS_GEOJSON,
)

QUERY = """
SELECT
    p.osm_id,
    ST_AsGeoJSON(p.way)::json  AS geometry_json,
    p.building,
    p.name,
    -- Flatten hstore tags into individual columns
    p.tags -> 'height'               AS height,
    p.tags -> 'building:levels'      AS building_levels,
    p.tags -> 'min_height'           AS min_height,
    p.tags -> 'building:min_level'   AS building_min_level,
    p.tags -> 'roof:height'          AS roof_height,
    p.tags -> 'roof:levels'          AS roof_levels
FROM planet_osm_polygon p
WHERE p.building IS NOT NULL OR p.tags ? 'building'
"""


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    url = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
    engine = create_engine(url)

    print("Connecting to PostgreSQL…")
    with engine.connect() as conn:
        df = pd.read_sql(text(QUERY), conn)
    print(f"  {len(df):,} buildings fetched.")

    # Build GeoDataFrame from WKT geometries
    import shapely.wkt
    from shapely.geometry import shape

    geoms = [shape(g) for g in df["geometry_json"]]
    gdf = gpd.GeoDataFrame(
        df.drop(columns=["geometry_json"]),
        geometry=geoms,
        crs="EPSG:4326",
    )

    gdf.to_file(BUILDINGS_GEOJSON, driver="GeoJSON")
    print(f"  Saved → {BUILDINGS_GEOJSON}")
    print(f"  Columns: {list(gdf.columns)}")


if __name__ == "__main__":
    main()
