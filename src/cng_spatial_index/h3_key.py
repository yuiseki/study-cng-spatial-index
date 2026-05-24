"""H3 hexagonal spatial index helpers."""

from __future__ import annotations

import json
from typing import Sequence

import h3


def h3_encode_point(lat: float, lon: float, resolution: int) -> str:
    return h3.latlng_to_cell(lat, lon, resolution)


def h3_disk_cells(lat: float, lon: float, k: int, resolution: int) -> list[str]:
    center = h3.latlng_to_cell(lat, lon, resolution)
    return list(h3.grid_disk(center, k))


def h3_encode_bbox(
    minx: float, miny: float, maxx: float, maxy: float, resolution: int
) -> list[str]:
    geojson = {
        "type": "Polygon",
        "coordinates": [[
            [minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]
        ]],
    }
    cells = list(h3.geo_to_cells(geojson, resolution))
    # geo_to_cells uses inner containment (cell center must be inside polygon).
    # For polygons smaller than an H3 cell, fall back to the centroid cell so
    # every feature is indexed at every resolution.
    if not cells:
        lat = (miny + maxy) / 2
        lon = (minx + maxx) / 2
        cells = [h3.latlng_to_cell(lat, lon, resolution)]
    return cells


def h3_encode_polygon_geojson(geojson_polygon: dict, resolution: int) -> list[str]:
    return list(h3.geo_to_cells(geojson_polygon, resolution))
