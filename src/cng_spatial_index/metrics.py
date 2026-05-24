"""Compute bench metrics from raw query results."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd


def parquet_stats(path: Path) -> dict[str, Any]:
    """Return file size and basic row/group stats via DuckDB."""
    import duckdb

    con = duckdb.connect()
    try:
        row_count = con.execute(f"SELECT COUNT(*) FROM read_parquet('{path}')").fetchone()[0]
        # parquet_file_metadata gives file-level stats in DuckDB 1.x
        rg_count = con.execute(f"""
            SELECT COUNT(*) FROM parquet_metadata('{path}')
        """).fetchone()[0]
        size = path.stat().st_size if path.exists() else 0
        return {
            "file_size_bytes": size,
            "row_count": row_count,
            "row_group_count": rg_count,
        }
    except Exception:
        pass
    finally:
        con.close()

    size = path.stat().st_size if path.exists() else 0
    return {"file_size_bytes": size, "row_count": 0, "row_group_count": None}


def false_positive_rate(candidate: int, actual: int) -> float | None:
    if candidate == 0:
        return None
    return round((candidate - actual) / candidate * 100, 1)


def build_summary_df(results: list[dict[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(results)


def write_summary(df: pd.DataFrame, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "summary.csv"
    md_path  = out_dir / "summary.md"

    df.to_csv(csv_path, index=False)

    md_lines = ["# CNG Spatial Index — Corridor Bench Summary\n"]
    md_lines.append(df.to_markdown(index=False))
    md_path.write_text("\n".join(md_lines))
    print(f"  summary.csv  → {csv_path}")
    print(f"  summary.md   → {md_path}")
