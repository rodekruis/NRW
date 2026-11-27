from __future__ import annotations

import numpy as np
from shapely.geometry.base import BaseGeometry

from pipelines.constants import MINIMUM_ADMIN_AREA_SHARE_IN_SPATIAL_EXTENT
from pipelines.infra.data_types.admin_area_types import AdminAreasSet
from pipelines.infra.data_types.loaded_data_types import RasterData
from pipelines.infra.utils.exposure import (
    create_raster_geometry_clipper,
    get_place_codes_overlapping_geometry,
)


def determine_spatial_extent(
    spatial_extent_geometry: BaseGeometry,
    admin_areas: AdminAreasSet,
    flood_depth_raster: RasterData,
) -> tuple[RasterData | None, list[str]]:
    """
    Clip the flood depth raster to the station's spatial extent geometry, and take the admin areas it overlaps as
    place codes. Return a tuple of (clipped_raster_data, place_codes); (None, []) when it overlaps no admin area.
    """
    place_codes = get_place_codes_overlapping_geometry(
        geometry=spatial_extent_geometry,
        admin_areas=admin_areas,
        minimum_share_of_admin_area=MINIMUM_ADMIN_AREA_SHARE_IN_SPATIAL_EXTENT,
    )
    if not place_codes:
        return None, []
    clipper = create_raster_geometry_clipper(
        geometry=spatial_extent_geometry, raster=flood_depth_raster
    )
    return clipper.clip(flood_depth_raster), place_codes


def has_flooded_cells(flood_depth: RasterData) -> bool:
    return bool(
        np.any((flood_depth.array > 0) & (flood_depth.array != flood_depth.nodata))
    )
