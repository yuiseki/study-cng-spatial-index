#!/usr/bin/env python3
"""
Export OSM Taito-ku point features from PostgreSQL to GeoJSON.

Output: data/raw/points_taito.geojson
This is one of the only scripts that requires PostgreSQL access.
"""

import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text
from shapely.geometry import shape

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from cng_spatial_index.config import (
    PG_HOST, PG_PORT, PG_DB, PG_USER, PG_PASSWORD,
    RAW_DIR, POINTS_GEOJSON,
)

# All OSM point features in Taito-ku bounding box
QUERY = """
SELECT
    p.osm_id,
    ST_AsGeoJSON(p.way)::json AS geometry_json,
    p.name,
    p.amenity,
    p.shop,
    p.tourism,
    p.historic,
    p.leisure
FROM planet_osm_point p
WHERE ST_Within(
    p.way,
    ST_MakeEnvelope(139.76, 35.69, 139.82, 35.74, 4326)
)
"""


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    url = f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}"
    engine = create_engine(url)

    print("Connecting to PostgreSQL…")
    with engine.connect() as conn:
        df = pd.read_sql(text(QUERY), conn)
    print(f"  {len(df):,} points fetched.")

    geoms = [shape(g) for g in df["geometry_json"]]
    gdf = gpd.GeoDataFrame(
        df.drop(columns=["geometry_json"]),
        geometry=geoms,
        crs="EPSG:4326",
    )

    gdf.to_file(POINTS_GEOJSON, driver="GeoJSON")
    print(f"  Saved → {POINTS_GEOJSON}")
    print(f"  Columns: {list(gdf.columns)}")


if __name__ == "__main__":
    main()
