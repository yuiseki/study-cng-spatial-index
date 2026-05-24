"""GeoHash spatial index helpers."""

from __future__ import annotations

import math

import pygeohash as gh


def geohash_encode(lat: float, lon: float, precision: int) -> str:
    return gh.encode(lat, lon, precision)


def geohash_decode(code: str) -> tuple[float, float]:
    """Return (lat, lon) center of a geohash."""
    return gh.decode(code)


def _geohash_neighbors(code: str) -> list[str]:
    """Return 8 neighbors of a geohash cell (4 cardinal + 4 diagonal)."""
    top    = gh.get_adjacent(code, "top")
    bottom = gh.get_adjacent(code, "bottom")
    right  = gh.get_adjacent(code, "right")
    left   = gh.get_adjacent(code, "left")
    return [
        top, bottom, right, left,
        gh.get_adjacent(top,    "right"),   # top-right
        gh.get_adjacent(top,    "left"),    # top-left
        gh.get_adjacent(bottom, "right"),   # bottom-right
        gh.get_adjacent(bottom, "left"),    # bottom-left
    ]


def geohash_encode_bbox(
    minx: float, miny: float, maxx: float, maxy: float, precision: int
) -> list[str]:
    """Return all geohash cells that cover the given bbox."""
    cells: set[str] = set()
    # sample corners + center to get initial seeds, then BFS expand
    seeds = [
        gh.encode(miny, minx, precision),
        gh.encode(miny, maxx, precision),
        gh.encode(maxy, minx, precision),
        gh.encode(maxy, maxx, precision),
        gh.encode((miny + maxy) / 2, (minx + maxx) / 2, precision),
    ]
    queue = list(set(seeds))
    visited: set[str] = set(queue)
    while queue:
        code = queue.pop()
        lat_c, lon_c = gh.decode(code)
        # decode_exactly gives (lat, lon, lat_err, lon_err)
        decoded = gh.decode_exactly(code)
        lat_err, lon_err = decoded[2], decoded[3]
        # check if this cell overlaps the bbox
        cell_miny, cell_maxy = lat_c - lat_err, lat_c + lat_err
        cell_minx, cell_maxx = lon_c - lon_err, lon_c + lon_err
        if cell_maxy < miny or cell_miny > maxy or cell_maxx < minx or cell_minx > maxx:
            continue
        cells.add(code)
        for neighbor in _geohash_neighbors(code):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return list(cells)
