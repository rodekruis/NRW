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
from pipelines.flood.extract_forecast import (
    determine_peak_lead_time,
    extract_median_discharge,
    TimeIntervalDischarge,
)
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


class CellReturnPeriodsPerLeadTime:
    """
    Return periods per GloFAS cell on the day a station peaks, computed once per lead time:
    stations that peak on the same day share them.
    """

    def __init__(
        self,
        netcdf_paths: list[str],
        return_period_curves: GlofasReturnPeriodCurves,
        maximum_return_period: float,
    ) -> None:
        self._netcdf_paths = netcdf_paths
        self._return_period_curves = return_period_curves
        self._maximum_return_period = maximum_return_period
        self._by_lead_time: dict[int, RasterData | None] = {}

    def on_peak_day(
        self,
        time_interval_discharges: list[TimeIntervalDischarge],
        temporal_extent: dict[str, list],
    ) -> RasterData | None:
        lead_time = determine_peak_lead_time(time_interval_discharges, temporal_extent)
        if lead_time not in self._by_lead_time:
            self._by_lead_time[lead_time] = determine_cell_return_periods(
                median_discharge=extract_median_discharge(
                    netcdf_paths=self._netcdf_paths, lead_time=lead_time
                ),
                return_period_curves=self._return_period_curves,
                maximum_return_period=self._maximum_return_period,
            )
        return self._by_lead_time[lead_time]


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

    Returns None without a gridded forecast on the grid of the curves, as with the mock forecasts.
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
    Without return periods per cell, the whole area takes the station's return period.

    Returns None when even the highest flood map shows no flooding inside the boundary: the
    flood maps do not cover the area.
    """
    station_return_period = _resolve_requested_return_period_value(
        time_interval_severities
    )
    highest_flood_map = flood_depth_provider.get_raster(
        max(flood_depth_provider.available_return_periods)
    )
    clipper = create_raster_geometry_clipper(boundary, highest_flood_map)
    if not has_flooded_cells(clipper.clip(highest_flood_map)):
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
        array=np.where(clipper.mask_array, flood_depth, highest_flood_map.nodata),
        transform=clipper.cropped_transform,
        crs=highest_flood_map.crs,
        nodata=highest_flood_map.nodata,
    )


def _determine_pixel_return_periods(
    cell_return_periods: RasterData | None,
    station_return_period: float | None,
    clipper: RasterAdminAreaClipper,
    regridding_method: RegriddingMethod,
) -> np.ndarray:
    if cell_return_periods is None or not np.isfinite(cell_return_periods.array).any():
        reason = (
            "no gridded forecast on the grid of the curves"
            if cell_return_periods is None
            else "no GloFAS cell in the country has a return period on this day, so the forecast is likely missing discharge"
        )
        log_warning(
            logger,
            LogTag.FLOOD_LOGIC,
            f"No return period per GloFAS cell ({reason}): using the station's return period for its whole area",
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
