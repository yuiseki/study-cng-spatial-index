"""Quadkey (Web Mercator tile) spatial index helpers."""

from __future__ import annotations

import mercantile


def quadkey_encode(lat: float, lon: float, zoom: int) -> str:
    tile = mercantile.tile(lon, lat, zoom)
    return mercantile.quadkey(tile)


def quadkey_encode_bbox(
    minx: float, miny: float, maxx: float, maxy: float, zoom: int
) -> list[str]:
    bounds = mercantile.LngLatBbox(west=minx, south=miny, east=maxx, north=maxy)
    return [mercantile.quadkey(t) for t in mercantile.tiles(minx, miny, maxx, maxy, zooms=zoom)]


def quadkey_to_tile(qk: str) -> mercantile.Tile:
    return mercantile.quadkey_to_tile(qk)


def quadkey_bounds(qk: str) -> mercantile.LngLatBbox:
    return mercantile.bounds(mercantile.quadkey_to_tile(qk))
