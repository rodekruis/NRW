from __future__ import annotations

import logging

import numpy as np
from shapely.geometry.base import BaseGeometry

from pipelines.flood.constants import (
    MINIMUM_FLOOD_DEPTH_METRES,
    MINIMUM_GUMBEL_SCALE_CUBIC_METRES_PER_SECOND,
    MINIMUM_RETURN_PERIOD_YEARS,
    MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES,
    REGRIDDING_METHOD,
)
from pipelines.flood.determine_alerts import TimeIntervalReturnPeriodSeverity
from pipelines.flood.determine_exposure import has_flooded_cells
from pipelines.flood.footprint_method import (
    compute_return_period,
    interpolate_flood_depth,
    regrid_return_period,
    RegriddingMethod,
)
from pipelines.infra.data_types.flood_depth_provider import FloodDepthProvider
from pipelines.infra.data_types.glofas_return_period_curves import (
    GlofasReturnPeriodCurves,
)
from pipelines.infra.data_types.loaded_data_types import RasterData
from pipelines.infra.utils.exposure import (
    create_raster_geometry_clipper,
    RasterAdminAreaClipper,
)
from pipelines.infra.utils.nrw_logger import log_warning, LogTag

logger = logging.getLogger(__name__)

_SQUARE_METRES_PER_SQUARE_KILOMETRE = 1_000_000.0


def determine_cell_return_periods(
    median_discharge: RasterData | None,
    return_period_curves: GlofasReturnPeriodCurves,
    maximum_return_period: float,
    minimum_upstream_area: float = MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES,
    minimum_gumbel_scale: float = MINIMUM_GUMBEL_SCALE_CUBIC_METRES_PER_SECOND,
) -> RasterData | None:
    """
    Return period per GloFAS cell, each on its own Gumbel curve. Cells that do not drive the
    footprint are NaN: no discharge, no curve, a small stream or a near-flat curve.

    Returns None when there is no gridded forecast on the grid of the curves, as with the mock
    forecasts. The footprint then falls back to the station's return period.
    """
    if median_discharge is None:
        return None

    try:
        curves = return_period_curves.aligned_to(
            median_discharge.transform, median_discharge.array.shape
        )
    except ValueError as error:
        log_warning(logger, LogTag.FLOOD_LOGIC, str(error))
        return None

    return_periods = compute_return_period(
        discharge=median_discharge.array,
        location=curves.location,
        scale=curves.scale,
        maximum_return_period=maximum_return_period,
    )
    with np.errstate(invalid="ignore"):
        drives_footprint = (
            np.isfinite(return_periods)
            & (curves.scale >= minimum_gumbel_scale)
            & (
                curves.upstream_area
                >= minimum_upstream_area * _SQUARE_METRES_PER_SQUARE_KILOMETRE
            )
        )

    return RasterData(
        array=np.where(drives_footprint, return_periods, np.nan),
        transform=median_discharge.transform,
        crs=median_discharge.crs,
        nodata=np.nan,
    )


def compute_flood_depth(
    time_interval_severities: list[TimeIntervalReturnPeriodSeverity],
    cell_return_periods: RasterData | None,
    boundary: BaseGeometry,
    flood_depth_provider: FloodDepthProvider,
    regridding_method: RegriddingMethod = REGRIDDING_METHOD,
    minimum_flood_depth: float = MINIMUM_FLOOD_DEPTH_METRES,
    minimum_return_period: float = MINIMUM_RETURN_PERIOD_YEARS,
) -> RasterData | None:
    """
    Compute the flood depth inside the boundary of an alert: each pixel takes the return period
    of the GloFAS cells around it, and its depth is interpolated between the flood maps. Pixels
    below minimum_return_period stay dry, and depths below minimum_flood_depth are left out.

    Returns None when the flood map for the station's return period shows no flooding inside the
    boundary: the station is mapped to an area the flood maps do not cover.
    """
    station_return_period = _resolve_requested_return_period_value(
        time_interval_severities
    )
    station_flood_map = _resolve_flood_depth_raster(
        return_period=station_return_period,
        flood_depth_provider=flood_depth_provider,
    )
    clipper = create_raster_geometry_clipper(boundary, station_flood_map)
    if not has_flooded_cells(clipper.clip(station_flood_map)):
        return None

    pixel_return_periods = _determine_pixel_return_periods(
        cell_return_periods=cell_return_periods,
        station_return_period=station_return_period,
        clipper=clipper,
        regridding_method=regridding_method,
    )
    flood_depth = interpolate_flood_depth(
        return_period=pixel_return_periods,
        load_flood_map=lambda return_period: _load_clipped_flood_map(
            return_period, flood_depth_provider, clipper
        ),
        available_return_periods=flood_depth_provider.available_return_periods,
        minimum_return_period=minimum_return_period,
    )
    flood_depth[flood_depth < minimum_flood_depth] = 0.0

    return RasterData(
        array=np.where(clipper.mask_array, flood_depth, station_flood_map.nodata),
        transform=clipper.cropped_transform,
        crs=station_flood_map.crs,
        nodata=station_flood_map.nodata,
    )


def _determine_pixel_return_periods(
    cell_return_periods: RasterData | None,
    station_return_period: float | None,
    clipper: RasterAdminAreaClipper,
    regridding_method: RegriddingMethod,
) -> np.ndarray:
    if cell_return_periods is None or not np.isfinite(cell_return_periods.array).any():
        log_warning(
            logger,
            LogTag.FLOOD_LOGIC,
            "No return period per GloFAS cell: using the station's return period for its whole area",
        )
        return np.full(
            clipper.mask_array.shape,
            np.nan if station_return_period is None else station_return_period,
            dtype=np.float32,
        )

    return regrid_return_period(
        return_period=cell_return_periods.array,
        source_transform=cell_return_periods.transform,
        target_transform=clipper.cropped_transform,
        target_shape=clipper.mask_array.shape,
        method=regridding_method,
        target_mask=clipper.mask_array,
    )


def _load_clipped_flood_map(
    return_period: int,
    flood_depth_provider: FloodDepthProvider,
    clipper: RasterAdminAreaClipper,
) -> np.ndarray:
    flood_map = clipper.clip(flood_depth_provider.get_raster(return_period))
    flood_map.array[flood_map.array == flood_map.nodata] = 0.0
    return flood_map.array


def _resolve_requested_return_period_value(
    time_interval_severities: list[TimeIntervalReturnPeriodSeverity],
) -> float | None:
    highest_return_period = max(
        time_interval_severities,
        key=lambda s: s.median_return_period,
    ).median_return_period

    if highest_return_period <= 0:
        return None

    return float(highest_return_period)


def _resolve_flood_depth_raster(
    return_period: float | None,
    flood_depth_provider: FloodDepthProvider,
) -> RasterData:
    """
    Resolve the flood depth raster using this order:
    1. Highest available return period that is <= the forecast return period.
    2. Lowest available return period overall (when forecast RP is below all available maps).
    3. Empty fallback raster (when no threshold is exceeded).
    """
    available = flood_depth_provider.available_return_periods

    if return_period is not None:
        highest_below_or_equal_to_forecast = max(
            (rp for rp in available if rp <= return_period),
            default=None,
        )
        if highest_below_or_equal_to_forecast is not None:
            return flood_depth_provider.get_raster(highest_below_or_equal_to_forecast)

        lowest_available_overall = min(available)
        return flood_depth_provider.get_raster(lowest_available_overall)

    return _create_empty_raster(flood_depth_provider)


def _create_empty_raster(flood_depth_provider: FloodDepthProvider) -> RasterData:
    """Create a zero-valued raster (indicating no flood) as fallback when no return period threshold is exceeded."""
    if not flood_depth_provider.available_return_periods:
        raise FileNotFoundError(
            "Could not resolve flood depth raster: no available return period "
            "rasters to derive an empty fallback from."
        )

    reference_return_period = flood_depth_provider.available_return_periods[0]
    reference_raster = flood_depth_provider.get_raster(reference_return_period)

    empty_array = np.zeros_like(reference_raster.array)

    return RasterData(
        array=empty_array,
        transform=reference_raster.transform,
        crs=reference_raster.crs,
        nodata=reference_raster.nodata,
    )
