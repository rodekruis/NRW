from __future__ import annotations

import numpy as np
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from pipelines.infra.data_types.admin_area_types import AdminAreasSet
from pipelines.infra.data_types.loaded_data_types import RasterData


def determine_spatial_extent(
    station_place_codes: list[str],
    admin_areas: AdminAreasSet,
) -> tuple[BaseGeometry | None, list[str]]:
    """
    Determine the area of an alert: the station place codes that are valid admin areas, and the
    boundary around them. The flood footprint is computed inside that boundary.
    Return a tuple of (boundary, place_codes).
    """
    valid_place_codes = [
        place_code
        for place_code in station_place_codes
        if place_code in admin_areas.admin_areas
    ]

    if not valid_place_codes:
        return None, []

    boundary = unary_union(
        [
            admin_areas.admin_areas[place_code].to_geometry()
            for place_code in valid_place_codes
        ]
    )

    return boundary, valid_place_codes


def has_flooded_cells(flood_depth: RasterData) -> bool:
    return bool(
        np.any((flood_depth.array > 0) & (flood_depth.array != flood_depth.nodata))
    )
