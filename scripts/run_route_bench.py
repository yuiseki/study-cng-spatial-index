#!/usr/bin/env python3
"""
Stage 2: A* grid route search benchmark.

Routes a drone from south to north through Taito-ku at each altitude,
comparing zfxy vs zxy_heightbin for blocked-cell lookup.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from cng_spatial_index.config import (
    PARQUET_DIR, RESULTS_DIR,
    OCCUPANCY_ZFXY_PARQUET, OCCUPANCY_ZXY_HEIGHTBIN_PARQUET,
    CORRIDOR_CENTER_LON, CORRIDOR_SOUTH_LAT, CORRIDOR_NORTH_LAT,
    ALTITUDES_M, CLEARANCE_M,
    ZFXY_Z_LEVELS, XY_Z, VERTICAL_BIN_M_LIST,
)
from cng_spatial_index.route import run_route_zfxy, run_route_zxy_heightbin
from cng_spatial_index.metrics import build_summary_df, write_summary


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out_dir = RESULTS_DIR / f"route_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Route Bench: {stamp} ===")

    results = []

    # ── zfxy ──────────────────────────────────────────────────────────────
    print("\n--- zfxy ---")
    for z in ZFXY_Z_LEVELS:
        for alt in ALTITUDES_M:
            r = run_route_zfxy(
                OCCUPANCY_ZFXY_PARQUET,
                CORRIDOR_CENTER_LON, CORRIDOR_SOUTH_LAT,
                CORRIDOR_CENTER_LON, CORRIDOR_NORTH_LAT,
                alt, CLEARANCE_M, z,
            )
            results.append({
                "scheme": "zfxy", "resolution": f"z={z}",
                "altitude_m": alt,
                "lookup_ms": r["lookup_ms"], "route_ms": r["route_ms"],
                "lookup_count": r["lookup_count"],
                "route_found": r["found"],
                "route_length": r["length"],
                "expanded_nodes": r["expanded"],
            })
            print(f"  z={z} alt={alt}m: found={r['found']} len={r['length']} "
                  f"expanded={r['expanded']} lookup={r['lookup_ms']}ms route={r['route_ms']}ms")

    # ── zxy_heightbin ──────────────────────────────────────────────────────
    print("\n--- zxy_heightbin ---")
    for vbin in VERTICAL_BIN_M_LIST:
        for alt in ALTITUDES_M:
            r = run_route_zxy_heightbin(
                OCCUPANCY_ZXY_HEIGHTBIN_PARQUET,
                CORRIDOR_CENTER_LON, CORRIDOR_SOUTH_LAT,
                CORRIDOR_CENTER_LON, CORRIDOR_NORTH_LAT,
                alt, CLEARANCE_M, XY_Z, vbin,
            )
            results.append({
                "scheme": "zxy_heightbin", "resolution": f"xy_z={XY_Z},vbin={vbin}m",
                "altitude_m": alt,
                "lookup_ms": r["lookup_ms"], "route_ms": r["route_ms"],
                "lookup_count": r["lookup_count"],
                "route_found": r["found"],
                "route_length": r["length"],
                "expanded_nodes": r["expanded"],
            })
            print(f"  vbin={vbin}m alt={alt}m: found={r['found']} len={r['length']} "
                  f"expanded={r['expanded']} lookup={r['lookup_ms']}ms route={r['route_ms']}ms")

    df = build_summary_df(results)
    write_summary(df, out_dir)
    (out_dir / "metadata.json").write_text(json.dumps({
        "timestamp": stamp,
        "type": "route_bench",
        "start": [CORRIDOR_CENTER_LON, CORRIDOR_SOUTH_LAT],
        "goal":  [CORRIDOR_CENTER_LON, CORRIDOR_NORTH_LAT],
        "altitudes": ALTITUDES_M,
        "clearance_m": CLEARANCE_M,
    }, indent=2))

    print(f"\n=== Done: {out_dir} ===")


if __name__ == "__main__":
    main()
