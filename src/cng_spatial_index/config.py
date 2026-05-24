"""Central configuration for paths, corridor, and bench parameters."""

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

DATA_DIR      = REPO_ROOT / "data"
RAW_DIR       = DATA_DIR / "raw"
PREPARED_DIR  = DATA_DIR / "prepared"
PARQUET_DIR   = DATA_DIR / "parquet"
RESULTS_DIR   = DATA_DIR / "results"

# Source PostgreSQL (study-pg-spatial-index zfxy container)
PG_HOST     = "localhost"
PG_PORT     = 55442
PG_DB       = "postgres"
PG_USER     = "postgres"
PG_PASSWORD = "postgres"

# Raw export filenames
BUILDINGS_GEOJSON = RAW_DIR / "buildings_taito.geojson"

# Prepared / obstacle data
OBSTACLES_GEOPARQUET = PREPARED_DIR / "building_obstacles.geoparquet"

# Parquet cell tables
OCCUPANCY_ZFXY_PARQUET        = PARQUET_DIR / "occupancy_zfxy.parquet"
OCCUPANCY_ZXY_HEIGHTBIN_PARQUET = PARQUET_DIR / "occupancy_zxy_heightbin.parquet"
OCCUPANCY_MORTON3D_PARQUET    = PARQUET_DIR / "occupancy_morton3d.parquet"

# -----------------------------------------------------------------------
# Height model
# -----------------------------------------------------------------------
DEFAULT_HEIGHT_M = 15.0
FLOOR_HEIGHT_M   = 3.0

# -----------------------------------------------------------------------
# Corridor definition (Taito-ku south → north)
# -----------------------------------------------------------------------
CORRIDOR_CENTER_LON = 139.785
CORRIDOR_SOUTH_LAT  = 35.695
CORRIDOR_NORTH_LAT  = 35.731
CORRIDOR_MINX       = 139.784450
CORRIDOR_MAXX       = 139.785550
CORRIDOR_MINY       = CORRIDOR_SOUTH_LAT
CORRIDOR_MAXY       = CORRIDOR_NORTH_LAT
CORRIDOR_WIDTH_M    = 100

ALTITUDES_M  = [30, 60, 90, 120]
CLEARANCE_M  = 5

# -----------------------------------------------------------------------
# Key design parameters
# -----------------------------------------------------------------------
ZFXY_Z_LEVELS        = [19, 20, 21, 22]

XY_Z                 = 19
VERTICAL_BIN_M_LIST  = [4, 8, 16]

# Safety caps for cell expansion
XY_CAP   = 200     # max (x_max - x_min + 1) * (y_max - y_min + 1)
FXY_CAP  = 1000    # max total 3D cells per building

# Parquet row group sizes to test
ROW_GROUP_SIZES = [10_000, 50_000, 100_000]
DEFAULT_ROW_GROUP_SIZE = 50_000

# -----------------------------------------------------------------------
# 2D index parameters
# -----------------------------------------------------------------------
H3_RESOLUTIONS    = [7, 8, 9, 10]
GEOHASH_PRECISIONS = [5, 6, 7, 8]
QUADKEY_ZOOMS     = [15, 17, 19]
MORTON2D_XY_Z     = 19   # tile zoom used for local_x/local_y normalization

# Raw point export
POINTS_GEOJSON = RAW_DIR / "points_taito.geojson"

# 2D cell Parquet tables (points)
CELLS_H3_POINTS_PARQUET       = PARQUET_DIR / "cells_h3_points.parquet"
CELLS_GEOHASH_POINTS_PARQUET  = PARQUET_DIR / "cells_geohash_points.parquet"
CELLS_QUADKEY_POINTS_PARQUET  = PARQUET_DIR / "cells_quadkey_points.parquet"
CELLS_MORTON2D_POINTS_PARQUET = PARQUET_DIR / "cells_morton2d_points.parquet"

# 2D cell Parquet tables (polygons / buildings)
CELLS_H3_POLY_PARQUET       = PARQUET_DIR / "cells_h3_poly.parquet"
CELLS_GEOHASH_POLY_PARQUET  = PARQUET_DIR / "cells_geohash_poly.parquet"
CELLS_QUADKEY_POLY_PARQUET  = PARQUET_DIR / "cells_quadkey_poly.parquet"
CELLS_MORTON2D_POLY_PARQUET = PARQUET_DIR / "cells_morton2d_poly.parquet"

# Flat bbox-columns GeoParquet (for DuckDB spatial + RTREE bench)
BBOX_POINTS_GEOPARQUET = PREPARED_DIR / "points_with_bbox.geoparquet"
BBOX_POLY_GEOPARQUET   = PREPARED_DIR / "poly_with_bbox.geoparquet"

# Viewport/radius bench parameters
VIEWPORT_LON_CENTER = 139.785
VIEWPORT_LAT_CENTER = 35.713
VIEWPORT_SIZES_DEG  = [0.01, 0.05, 0.1]   # ~1 km, ~5 km, ~10 km sides
RADIUS_M_LIST       = [500, 1000, 2000]
KNN_K               = 10
