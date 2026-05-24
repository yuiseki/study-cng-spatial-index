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
    return list(h3.geo_to_cells(geojson, resolution))


def h3_encode_polygon_geojson(geojson_polygon: dict, resolution: int) -> list[str]:
    return list(h3.geo_to_cells(geojson_polygon, resolution))
