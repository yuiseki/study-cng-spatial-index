"""Height estimation from OSM building tags."""

import re
from typing import Any

from .config import DEFAULT_HEIGHT_M, FLOOR_HEIGHT_M


def parse_height_m(raw: str | None) -> float | None:
    """Parse an OSM height string to metres.

    Handles:
        "12"         → 12.0
        "12 m"       → 12.0
        "12.5"       → 12.5
        "30 ft"      → 9.14
        "10;12"      → 10.0  (first value)
        unparseable  → None
    """
    if raw is None:
        return None
    raw = str(raw).strip()
    if not raw:
        return None

    # Take first value if semicolon-separated
    first = raw.split(";")[0].strip()

    # Feet → metres
    if re.search(r"\s*(ft|feet|foot)\s*$", first, re.IGNORECASE):
        num = re.sub(r"\s*(ft|feet|foot)\s*$", "", first, flags=re.IGNORECASE).strip()
        try:
            val = float(num) * 0.3048
            if 0 < val < 9999:
                return round(val, 2)
        except (ValueError, TypeError):
            pass
        return None

    # Strip metric suffix
    cleaned = re.sub(r"\s*(m|meters?|metres?)\s*$", "", first, flags=re.IGNORECASE).strip()
    try:
        val = float(cleaned)
        if 0 < val < 9999:
            return val
    except (ValueError, TypeError):
        pass
    return None


def parse_levels(raw: str | None) -> float | None:
    """Parse building:levels to a float. Returns None if not parseable."""
    if raw is None:
        return None
    try:
        val = float(str(raw).strip())
        if 0 < val < 500:
            return val
    except (ValueError, TypeError):
        pass
    return None


def estimate_heights(
    tags: dict[str, Any],
    default_height_m: float = DEFAULT_HEIGHT_M,
    floor_height_m: float = FLOOR_HEIGHT_M,
) -> dict[str, Any]:
    """Estimate max_height_m / min_height_m / height_source from OSM tags.

    Args:
        tags: hstore dict or flat dict with OSM tag keys
        default_height_m: fallback height when no tag is available
        floor_height_m: metres per floor for building:levels estimation

    Returns:
        dict with keys: max_height_m, min_height_m, height_source, levels, min_level
    """
    # max_height_m
    max_h = parse_height_m(tags.get("height"))
    if max_h is not None:
        source = "height"
    else:
        levels = parse_levels(tags.get("building:levels"))
        if levels is not None:
            max_h = levels * floor_height_m
            source = "building:levels_estimated"
        else:
            max_h = default_height_m
            source = "default_15m"

    # min_height_m
    min_h = parse_height_m(tags.get("min_height"))
    if min_h is None:
        min_level = parse_levels(tags.get("building:min_level"))
        min_h = (min_level * floor_height_m) if min_level is not None else 0.0
    else:
        min_level = None

    levels_val = parse_levels(tags.get("building:levels"))
    min_level_val = parse_levels(tags.get("building:min_level"))

    return {
        "max_height_m": max_h,
        "min_height_m": min_h,
        "height_source": source,
        "levels": levels_val,
        "min_level": min_level_val,
    }
