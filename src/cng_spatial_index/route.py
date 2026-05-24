"""Grid-based A* route search using DuckDB/Parquet occupancy lookups.

Stage 2 (minimal implementation): 2D grid at fixed altitude.
Each node = (x, y) tile at a given hbin or f level.
Blocked status is looked up from the occupancy Parquet files.

The route module separates:
    - lookup cost  (DuckDB Parquet reads)
    - algorithm cost (A* expansion)
"""

from __future__ import annotations

import heapq
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import duckdb
import numpy as np


@dataclass(order=True)
class _Node:
    priority: float
    x: int = field(compare=False)
    y: int = field(compare=False)


def _heuristic(x1: int, y1: int, x2: int, y2: int) -> float:
    return abs(x2 - x1) + abs(y2 - y1)


def _load_blocked_set_zfxy(
    parquet_path: Path, z: int, f_min: int, f_max: int,
    x_min: int, x_max: int, y_min: int, y_max: int,
) -> set[tuple[int, int]]:
    sql = f"""
        SELECT DISTINCT x, y
        FROM read_parquet('{parquet_path}')
        WHERE f BETWEEN {f_min} AND {f_max}
          AND x BETWEEN {x_min} AND {x_max}
          AND y BETWEEN {y_min} AND {y_max}
    """
    con = duckdb.connect()
    rows = con.execute(sql).fetchall()
    con.close()
    return {(r[0], r[1]) for r in rows}


def _load_blocked_set_zxy_heightbin(
    parquet_path: Path, xy_z: int, vertical_bin_m: float,
    hbin_min: int, hbin_max: int,
    x_min: int, x_max: int, y_min: int, y_max: int,
) -> set[tuple[int, int]]:
    sql = f"""
        SELECT DISTINCT x, y
        FROM read_parquet('{parquet_path}')
        WHERE xy_z = {xy_z}
          AND vertical_bin_m = {vertical_bin_m}
          AND hbin BETWEEN {hbin_min} AND {hbin_max}
          AND x BETWEEN {x_min} AND {x_max}
          AND y BETWEEN {y_min} AND {y_max}
    """
    con = duckdb.connect()
    rows = con.execute(sql).fetchall()
    con.close()
    return {(r[0], r[1]) for r in rows}


def astar_route(
    start_xy: tuple[int, int],
    goal_xy: tuple[int, int],
    blocked: set[tuple[int, int]],
    x_min: int, x_max: int,
    y_min: int, y_max: int,
    neighbors_8: bool = False,
) -> dict[str, Any]:
    """A* on a 2D tile grid. Returns path or failure metrics."""
    sx, sy = start_xy
    gx, gy = goal_xy

    open_heap: list[_Node] = [_Node(0.0, sx, sy)]
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {(sx, sy): None}
    g_score: dict[tuple[int, int], float] = {(sx, sy): 0.0}
    expanded = 0

    if neighbors_8:
        deltas = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
    else:
        deltas = [(-1,0),(1,0),(0,-1),(0,1)]

    while open_heap:
        current = heapq.heappop(open_heap)
        cx, cy = current.x, current.y
        expanded += 1

        if (cx, cy) == (gx, gy):
            # Reconstruct path
            path = []
            node = (gx, gy)
            while node is not None:
                path.append(node)
                node = came_from[node]
            path.reverse()
            return {"found": True, "path": path, "length": len(path), "expanded": expanded}

        for dx, dy in deltas:
            nx, ny = cx + dx, cy + dy
            if not (x_min <= nx <= x_max and y_min <= ny <= y_max):
                continue
            if (nx, ny) in blocked:
                continue
            new_g = g_score[(cx, cy)] + (1.4142 if abs(dx) + abs(dy) == 2 else 1.0)
            if (nx, ny) not in g_score or new_g < g_score[(nx, ny)]:
                g_score[(nx, ny)] = new_g
                f = new_g + _heuristic(nx, ny, gx, gy)
                heapq.heappush(open_heap, _Node(f, nx, ny))
                came_from[(nx, ny)] = (cx, cy)

    return {"found": False, "path": [], "length": 0, "expanded": expanded}


def run_route_zfxy(
    parquet_path: Path,
    start_lon: float, start_lat: float,
    goal_lon: float,  goal_lat: float,
    altitude_m: float, clearance_m: float,
    z: int,
) -> dict[str, Any]:
    from .zfxy import zfxy_x, zfxy_y, zfxy_f

    sx = zfxy_x(start_lon, z);  sy = zfxy_y(start_lat, z)
    gx = zfxy_x(goal_lon,  z);  gy = zfxy_y(goal_lat,  z)
    f_min = zfxy_f(altitude_m - clearance_m, z)
    f_max = zfxy_f(altitude_m + clearance_m, z)

    # Bounding box = min of start/goal ± 2 tiles
    x_lo = min(sx, gx) - 2;  x_hi = max(sx, gx) + 2
    y_lo = min(sy, gy) - 2;  y_hi = max(sy, gy) + 2

    t_lookup = time.perf_counter()
    blocked = _load_blocked_set_zfxy(parquet_path, z, f_min, f_max, x_lo, x_hi, y_lo, y_hi)
    lookup_ms = (time.perf_counter() - t_lookup) * 1000

    t_route = time.perf_counter()
    result = astar_route((sx, sy), (gx, gy), blocked, x_lo, x_hi, y_lo, y_hi)
    route_ms = (time.perf_counter() - t_route) * 1000

    return {
        "scheme": "zfxy", "z": z, "vertical_bin_m": None,
        "altitude_m": altitude_m, "f_min": f_min, "f_max": f_max,
        "lookup_ms": round(lookup_ms, 3),
        "route_ms": round(route_ms, 3),
        "lookup_count": len(blocked),
        **result,
    }


def run_route_zxy_heightbin(
    parquet_path: Path,
    start_lon: float, start_lat: float,
    goal_lon: float,  goal_lat: float,
    altitude_m: float, clearance_m: float,
    xy_z: int, vertical_bin_m: float,
) -> dict[str, Any]:
    from .zxy_heightbin import zxy_x, zxy_y, height_bin

    sx = zxy_x(start_lon, xy_z);  sy = zxy_y(start_lat, xy_z)
    gx = zxy_x(goal_lon,  xy_z);  gy = zxy_y(goal_lat,  xy_z)
    hbin_min = height_bin(altitude_m - clearance_m, vertical_bin_m)
    hbin_max = height_bin(altitude_m + clearance_m, vertical_bin_m)

    x_lo = min(sx, gx) - 2;  x_hi = max(sx, gx) + 2
    y_lo = min(sy, gy) - 2;  y_hi = max(sy, gy) + 2

    t_lookup = time.perf_counter()
    blocked = _load_blocked_set_zxy_heightbin(
        parquet_path, xy_z, vertical_bin_m, hbin_min, hbin_max, x_lo, x_hi, y_lo, y_hi
    )
    lookup_ms = (time.perf_counter() - t_lookup) * 1000

    t_route = time.perf_counter()
    result = astar_route((sx, sy), (gx, gy), blocked, x_lo, x_hi, y_lo, y_hi)
    route_ms = (time.perf_counter() - t_route) * 1000

    return {
        "scheme": "zxy_heightbin", "z": xy_z, "vertical_bin_m": vertical_bin_m,
        "altitude_m": altitude_m, "hbin_min": hbin_min, "hbin_max": hbin_max,
        "lookup_ms": round(lookup_ms, 3),
        "route_ms": round(route_ms, 3),
        "lookup_count": len(blocked),
        **result,
    }
