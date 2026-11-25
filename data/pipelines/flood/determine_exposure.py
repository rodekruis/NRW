from __future__ import annotations

import numpy as np
from shapely.geometry.base import BaseGeometry

from pipelines.flood.constants import MINIMUM_ADMIN_AREA_SHARE_IN_SPATIAL_EXTENT
from pipelines.infra.data_types.admin_area_types import AdminAreasSet
from pipelines.infra.data_types.loaded_data_types import RasterData
from pipelines.infra.data_types.location_point import LocationPoint
from pipelines.infra.utils.exposure import (
    clip_raster_to_admin_areas,
    create_raster_geometry_clipper,
    get_place_codes_overlapping_geometry,
)


def determine_spatial_extent(
    station: LocationPoint,
    station_place_codes: list[str],
    admin_areas: AdminAreasSet,
    flood_depth_raster: RasterData,
    spatial_extent_geometry: BaseGeometry | None = None,
) -> tuple[RasterData | None, list[str]]:
    """
    Determine spatial extent by filtering station place codes to valid admin areas, clipping the flood depth raster.
    With a spatial extent geometry, the flood depth is clipped to that geometry instead, and the place codes are
    the admin areas it overlaps; the station place codes are then not used.
    Return a tuple of (clipped_raster_data, place_codes).
    """
    if spatial_extent_geometry is not None:
        return _determine_spatial_extent_from_geometry(
            spatial_extent_geometry, admin_areas, flood_depth_raster
        )

    valid_place_codes = [
        place_code
        for place_code in station_place_codes
        if place_code in admin_areas.admin_areas
    ]

    if not valid_place_codes:
        return None, []

    clipped_flood_depth = clip_flood_depth_to_admin_areas(
        place_codes=valid_place_codes,
        admin_areas=admin_areas,
        flood_depth_raster=flood_depth_raster,
        station_code=station.id,
    )

    return clipped_flood_depth, valid_place_codes


def _determine_spatial_extent_from_geometry(
    spatial_extent_geometry: BaseGeometry,
    admin_areas: AdminAreasSet,
    flood_depth_raster: RasterData,
) -> tuple[RasterData | None, list[str]]:
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


def clip_flood_depth_to_admin_areas(
    place_codes: list[str],
    admin_areas: AdminAreasSet,
    flood_depth_raster: RasterData,
    station_code: str,
) -> RasterData:
    return clip_raster_to_admin_areas(
        place_codes=place_codes,
        admin_areas=admin_areas,
        raster=flood_depth_raster,
        label=f"station {station_code}",
    )
