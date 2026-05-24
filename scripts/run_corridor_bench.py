#!/usr/bin/env python3
"""
Stage 1: Corridor lookup benchmark.

Runs DuckDB queries on occupancy Parquet files for each scheme
at multiple altitude levels, then writes results.
"""

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from cng_spatial_index.config import (
    PARQUET_DIR, RESULTS_DIR,
    OCCUPANCY_ZFXY_PARQUET, OCCUPANCY_ZXY_HEIGHTBIN_PARQUET, OCCUPANCY_MORTON3D_PARQUET,
    OBSTACLES_GEOPARQUET,
    CORRIDOR_MINX, CORRIDOR_MINY, CORRIDOR_MAXX, CORRIDOR_MAXY,
    ALTITUDES_M, CLEARANCE_M,
    ZFXY_Z_LEVELS, XY_Z, VERTICAL_BIN_M_LIST,
)
from cng_spatial_index.duckdb_queries import (
    query_corridor_zfxy,
    query_corridor_zxy_heightbin,
    query_corridor_morton3d,
)
from cng_spatial_index.metrics import parquet_stats, false_positive_rate, build_summary_df, write_summary


def load_morton_meta() -> dict:
    import json
    meta_path = PARQUET_DIR / "morton3d_meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text())
    return {"xy_z": XY_Z, "x_origin": 0, "y_origin": 0}


def actual_blocking_buildings(altitude_m: float, clearance_m: float) -> int:
    """Count buildings that actually penetrate the corridor altitude band."""
    con = duckdb.connect()
    try:
        result = con.execute(f"""
            SELECT COUNT(*) FROM read_parquet('{OBSTACLES_GEOPARQUET}')
            WHERE xmin <= {CORRIDOR_MAXX}
              AND xmax >= {CORRIDOR_MINX}
              AND ymin <= {CORRIDOR_MAXY}
              AND ymax >= {CORRIDOR_MINY}
              AND max_height_m >= {altitude_m - clearance_m}
              AND min_height_m <= {altitude_m + clearance_m}
        """).fetchone()[0]
    finally:
        con.close()
    return result


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out_dir = RESULTS_DIR / stamp
    explain_dir = out_dir / "explain"
    queries_dir = out_dir / "queries"
    explain_dir.mkdir(parents=True, exist_ok=True)
    queries_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Corridor Bench: {stamp} ===")
    print(f"Output: {out_dir}")

    morton_meta = load_morton_meta()
    x_origin = morton_meta["x_origin"]
    y_origin = morton_meta["y_origin"]

    # Parquet file stats
    stats = {
        "zfxy":         parquet_stats(OCCUPANCY_ZFXY_PARQUET),
        "zxy_heightbin": parquet_stats(OCCUPANCY_ZXY_HEIGHTBIN_PARQUET),
        "morton3d":     parquet_stats(OCCUPANCY_MORTON3D_PARQUET),
    }

    print("\n--- Parquet file sizes ---")
    for scheme, s in stats.items():
        mb = s["file_size_bytes"] / 1e6
        print(f"  {scheme}: {s['row_count']:,} rows, {s['row_group_count']} row groups, {mb:.2f} MB")

    results = []

    # ── zfxy ──────────────────────────────────────────────────────────────
    print("\n--- zfxy ---")
    for z in ZFXY_Z_LEVELS:
        for alt in ALTITUDES_M:
            r = query_corridor_zfxy(
                OCCUPANCY_ZFXY_PARQUET,
                CORRIDOR_MINX, CORRIDOR_MINY, CORRIDOR_MAXX, CORRIDOR_MAXY,
                alt, CLEARANCE_M, z,
            )
            actual = actual_blocking_buildings(alt, CLEARANCE_M)
            fp = false_positive_rate(r["candidate_buildings"], actual)
            row = {
                "scheme": "zfxy",
                "resolution": f"z={z}",
                "altitude_m": alt,
                "candidate_cells": r["candidate_cells"],
                "candidate_buildings": r["candidate_buildings"],
                "actual_blocking_buildings": actual,
                "false_positive_pct": fp,
                "parquet_file_size_mb": round(stats["zfxy"]["file_size_bytes"] / 1e6, 2),
                "row_group_count": stats["zfxy"]["row_group_count"],
                "query_time_ms": r["query_time_ms"],
                "f_min": r.get("f_min"), "f_max": r.get("f_max"),
            }
            results.append(row)
            print(f"  z={z} alt={alt}m: {r['candidate_buildings']} cands / {actual} actual  {r['query_time_ms']}ms")

            fname = f"zfxy_z{z}_alt{alt}m.txt"
            (explain_dir / fname).write_text(r["explain"])
            (queries_dir / fname.replace(".txt", ".sql")).write_text(r["sql"])

    # ── zxy_heightbin ──────────────────────────────────────────────────────
    print("\n--- zxy_heightbin ---")
    for vbin in VERTICAL_BIN_M_LIST:
        for alt in ALTITUDES_M:
            r = query_corridor_zxy_heightbin(
                OCCUPANCY_ZXY_HEIGHTBIN_PARQUET,
                CORRIDOR_MINX, CORRIDOR_MINY, CORRIDOR_MAXX, CORRIDOR_MAXY,
                alt, CLEARANCE_M, XY_Z, vbin,
            )
            actual = actual_blocking_buildings(alt, CLEARANCE_M)
            fp = false_positive_rate(r["candidate_buildings"], actual)
            row = {
                "scheme": "zxy_heightbin",
                "resolution": f"xy_z={XY_Z},vbin={vbin}m",
                "altitude_m": alt,
                "candidate_cells": r["candidate_cells"],
                "candidate_buildings": r["candidate_buildings"],
                "actual_blocking_buildings": actual,
                "false_positive_pct": fp,
                "parquet_file_size_mb": round(stats["zxy_heightbin"]["file_size_bytes"] / 1e6, 2),
                "row_group_count": stats["zxy_heightbin"]["row_group_count"],
                "query_time_ms": r["query_time_ms"],
                "hbin_min": r.get("hbin_min"), "hbin_max": r.get("hbin_max"),
            }
            results.append(row)
            print(f"  vbin={vbin}m alt={alt}m: {r['candidate_buildings']} cands / {actual} actual  {r['query_time_ms']}ms")

            fname = f"zxy_heightbin_vbin{int(vbin)}m_alt{alt}m.txt"
            (explain_dir / fname).write_text(r["explain"])
            (queries_dir / fname.replace(".txt", ".sql")).write_text(r["sql"])

    # ── Morton3D ──────────────────────────────────────────────────────────
    print("\n--- Morton3D ---")
    for vbin in VERTICAL_BIN_M_LIST:
        for alt in ALTITUDES_M:
            r = query_corridor_morton3d(
                OCCUPANCY_MORTON3D_PARQUET,
                CORRIDOR_MINX, CORRIDOR_MINY, CORRIDOR_MAXX, CORRIDOR_MAXY,
                alt, CLEARANCE_M, XY_Z, vbin, x_origin, y_origin,
            )
            actual = actual_blocking_buildings(alt, CLEARANCE_M)
            fp = false_positive_rate(r["candidate_buildings"], actual)
            row = {
                "scheme": "morton3d",
                "resolution": f"xy_z={XY_Z},vbin={vbin}m",
                "altitude_m": alt,
                "candidate_cells": r["candidate_cells"],
                "candidate_buildings": r["candidate_buildings"],
                "actual_blocking_buildings": actual,
                "false_positive_pct": fp,
                "parquet_file_size_mb": round(stats["morton3d"]["file_size_bytes"] / 1e6, 2),
                "row_group_count": stats["morton3d"]["row_group_count"],
                "query_time_ms": r["query_time_ms"],
                "n_morton_ranges": r.get("n_morton_ranges"),
            }
            results.append(row)
            print(f"  vbin={vbin}m alt={alt}m: {r['candidate_buildings']} cands / {actual} actual  {r['query_time_ms']}ms  n_ranges={r.get('n_morton_ranges')}")

            fname = f"morton3d_vbin{int(vbin)}m_alt{alt}m.txt"
            (explain_dir / fname).write_text(r["explain"])
            (queries_dir / fname.replace(".txt", ".sql")).write_text(r["sql"])

    # ── Summary ──────────────────────────────────────────────────────────
    df = build_summary_df(results)
    write_summary(df, out_dir)

    # Metadata
    con = duckdb.connect()
    bcount = con.execute(f"SELECT COUNT(*) FROM read_parquet('{OBSTACLES_GEOPARQUET}')").fetchone()[0]
    dv = duckdb.__version__
    con.close()

    metadata = {
        "timestamp": stamp,
        "dataset": "OSM Taito-ku",
        "building_count": bcount,
        "height_policy": "default_15m",
        "schemes": ["zfxy", "zxy_heightbin", "morton3d"],
        "altitudes": ALTITUDES_M,
        "clearance_m": CLEARANCE_M,
        "corridor_width_m": 100,
        "corridor_minx": CORRIDOR_MINX,
        "corridor_maxx": CORRIDOR_MAXX,
        "corridor_miny": CORRIDOR_MINY,
        "corridor_maxy": CORRIDOR_MAXY,
        "zfxy_z_levels": ZFXY_Z_LEVELS,
        "xy_z": XY_Z,
        "vertical_bin_m_list": VERTICAL_BIN_M_LIST,
        "duckdb_version": dv,
        "parquet_stats": {k: v for k, v in stats.items()},
    }
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    print(f"\n=== Done: {out_dir} ===")


if __name__ == "__main__":
    main()
