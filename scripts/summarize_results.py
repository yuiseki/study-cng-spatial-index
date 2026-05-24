#!/usr/bin/env python3
"""
Aggregate all corridor/route bench results into a single summary.
"""

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from cng_spatial_index.config import RESULTS_DIR


def main() -> None:
    csv_files = sorted(RESULTS_DIR.rglob("summary.csv"))
    if not csv_files:
        print("No summary.csv files found in", RESULTS_DIR)
        return

    frames = []
    for f in csv_files:
        df = pd.read_csv(f)
        df["source"] = f.parent.name
        frames.append(df)

    all_df = pd.concat(frames, ignore_index=True)
    out = RESULTS_DIR / "all_results.csv"
    all_df.to_csv(out, index=False)
    print(f"Aggregated {len(csv_files)} result files → {out}")

    # Print corridor bench subset
    if "candidate_buildings" in all_df.columns:
        print("\n=== Corridor bench (latest) ===")
        latest = all_df[all_df["source"] == sorted(
            f.parent.name for f in csv_files if "route" not in f.parent.name
        )[-1]]
        cols = [c for c in ["scheme","resolution","altitude_m","candidate_buildings",
                             "actual_blocking_buildings","false_positive_pct","query_time_ms"]
                if c in latest.columns]
        print(latest[cols].to_string(index=False))


if __name__ == "__main__":
    main()
