from __future__ import annotations

import logging
import os
import re
import warnings
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC

import numpy as np
import rasterio
from rasterio.io import DatasetReader

from pipelines.constants import DEFAULT_CRS
from pipelines.flood.constants import (
    WATER_DISCHARGE_HIGH_PERCENTILE,
    WATER_DISCHARGE_LOW_PERCENTILE,
)
from pipelines.infra.data_types.dtos import WaterDischargeTimeSeriesEntry
from pipelines.infra.data_types.loaded_data_types import RasterData
from pipelines.infra.data_types.location_point import LocationPoint
from pipelines.infra.utils.nrw_logger import log_info, log_warning, LogTag

logger = logging.getLogger(__name__)


@dataclass
class TimeIntervalDischarge:
    time_interval_start: str
    time_interval_end: str
    ensemble_discharges: list[float]


StationDischarges = dict[str, list[TimeIntervalDischarge]]


def extract_discharge_glofas_station(
    station_code: str,
    station: LocationPoint,
    netcdf_paths: list[str],
    temporal_extent: dict[str, list],
) -> StationDischarges:
    """
    Sample discharge from pre-sliced GloFAS NetCDF files at station coordinates.

    Each NetCDF file represents one ensemble member. Each band within the file
    represents a lead time (band index = lead_time + 1).

    Returns a dict containing one entry: station_code -> list of lead-time discharge
    objects. Each lead-time object contains the time interval and one discharge per
    ensemble.
    """
    lead_time_min, lead_time_max = _parse_lead_time_range(temporal_extent)
    discharges: StationDischarges = {station_code: []}

    forecast_base_datetime: datetime | None = None

    for netcdf_path in netcdf_paths:
        # TODO: to catch exact today date netcdf file
        if not os.path.exists(netcdf_path):
            log_warning(
                logger,
                LogTag.FLOOD_LOGIC,
                f"NetCDF file not found, skipping: {netcdf_path}",
            )
            continue

        if forecast_base_datetime is None:
            forecast_base_datetime = _extract_forecast_base_datetime(netcdf_path)
            for lead_time in range(lead_time_min, lead_time_max + 1):
                time_interval_start, time_interval_end = _lead_time_to_time_interval(
                    forecast_base_datetime,
                    lead_time,
                )
                discharges[station_code].append(
                    TimeIntervalDischarge(
                        time_interval_start=time_interval_start,
                        time_interval_end=time_interval_end,
                        ensemble_discharges=[],
                    )
                )

        log_info(
            logger,
            LogTag.FLOOD_LOGIC,
            f"Extracting station discharge from {netcdf_path}",
        )
        with rasterio.open(netcdf_path) as src:
            station_coords = [(float(station.lon), float(station.lat))]
            for lead_time in range(lead_time_min, lead_time_max + 1):
                discharge_sampled = list(
                    src.sample(station_coords, indexes=lead_time + 1)
                )
                discharge_value = float(discharge_sampled[0][0])
                discharges[station_code][lead_time].ensemble_discharges.append(
                    discharge_value
                )

    return discharges


def determine_peak_lead_time(
    time_interval_discharges: list[TimeIntervalDischarge],
    temporal_extent: dict[str, list],
) -> int:
    """
    The lead time in days at which the station's ensemble-median discharge is highest, the
    earliest one when several are equally high. The flood footprint is computed for that day.
    """
    lead_time_min, _ = _parse_lead_time_range(temporal_extent)
    median_discharges = [
        (
            float(np.nanmedian(ensemble_discharges))
            if not np.isnan(ensemble_discharges).all()
            else -np.inf
        )
        for ensemble_discharges in (
            np.asarray(time_interval_discharge.ensemble_discharges, dtype=float)
            for time_interval_discharge in time_interval_discharges
        )
    ]
    if not median_discharges or max(median_discharges) == -np.inf:
        raise ValueError("No discharge to determine the peak lead time from")
    return lead_time_min + int(np.argmax(median_discharges))


def extract_median_discharge(
    netcdf_paths: list[str],
    lead_time: int,
) -> RasterData | None:
    """
    Per GloFAS cell, the ensemble-median discharge at one lead time (days).

    Returns None when there is no gridded forecast to read. Cells without discharge are NaN.
    """
    band_index = lead_time + 1
    existing_paths = [path for path in netcdf_paths if os.path.exists(path)]

    with ExitStack() as stack:
        datasets = [stack.enter_context(rasterio.open(path)) for path in existing_paths]
        datasets = [dataset for dataset in datasets if band_index <= dataset.count]
        if not datasets:
            return None

        reference = datasets[0]
        datasets_on_reference_grid = [
            dataset
            for dataset in datasets
            if dataset.shape == reference.shape
            and dataset.transform == reference.transform
        ]
        if len(datasets_on_reference_grid) < len(datasets):
            log_warning(
                logger,
                LogTag.FLOOD_LOGIC,
                f"Skipped {len(datasets) - len(datasets_on_reference_grid)} GloFAS files on a different grid",
            )

        ensemble_discharges = np.stack(
            [
                _read_discharge_band(dataset, band_index)
                for dataset in datasets_on_reference_grid
            ]
        )
        with warnings.catch_warnings():
            # Cells without discharge in any ensemble member stay NaN.
            warnings.simplefilter("ignore", category=RuntimeWarning)
            median_discharge = np.nanmedian(ensemble_discharges, axis=0)

        return RasterData(
            array=median_discharge,
            transform=reference.transform,
            crs=DEFAULT_CRS,
            nodata=np.nan,
        )


def _read_discharge_band(dataset: DatasetReader, band_index: int) -> np.ndarray:
    discharge = dataset.read(band_index, masked=True).astype(np.float32).filled(np.nan)
    # Fill values that the file does not declare as such are negative.
    discharge[discharge < 0] = np.nan
    return discharge


def build_water_discharge_time_series(
    time_interval_discharges: list[TimeIntervalDischarge],
) -> list[WaterDischargeTimeSeriesEntry]:
    """Build the raw discharge time series (median + low/high range, m3/s) for the full lead-time spectrum."""
    time_series: list[WaterDischargeTimeSeriesEntry] = []
    for time_interval_discharge in time_interval_discharges:
        ensemble_array = np.asarray(
            time_interval_discharge.ensemble_discharges,
            dtype=float,
        )
        # Skip intervals with no data; a fully-empty series is caught by alert integrity checks later.
        if ensemble_array.size == 0 or np.isnan(ensemble_array).all():
            continue
        time_series.append(
            WaterDischargeTimeSeriesEntry(
                start=time_interval_discharge.time_interval_start,
                end=time_interval_discharge.time_interval_end,
                median=float(np.nanmedian(ensemble_array)),
                low=float(
                    np.nanpercentile(ensemble_array, WATER_DISCHARGE_LOW_PERCENTILE)
                ),
                high=float(
                    np.nanpercentile(ensemble_array, WATER_DISCHARGE_HIGH_PERCENTILE)
                ),
            )
        )
    return time_series


def _parse_lead_time_range(temporal_extent: dict[str, list]) -> tuple[int, int]:
    """Parse a flood temporal extent into (lead_time_min, lead_time_max).

    Expects {"lead-time-spectrum": ["0-day", "1-day", ..., "7-day"]}.
    Returns (0, 7) for that example.
    """
    spectrum = temporal_extent.get("lead-time-spectrum")
    if not spectrum:
        raise ValueError(
            f"Temporal extent missing 'lead-time-spectrum': {temporal_extent}"
        )
    days = [int(entry.split("-")[0]) for entry in spectrum]
    return (min(days), max(days))


def _extract_forecast_base_datetime(netcdf_path: str) -> datetime:
    """Extract forecast run datetime from a file name like dis_00_2026040800_sliced.nc."""  # TODO: extract date 0 from nc dims instead
    basename = os.path.basename(netcdf_path)
    match = re.search(r"_(\d{10})_sliced(?:_[A-Z]{3})?\.nc$", basename)
    if match is None:
        raise ValueError(
            f"Unable to extract forecast date from NetCDF path: {netcdf_path}"
        )
    return datetime.strptime(match.group(1), "%Y%m%d%H").replace(tzinfo=UTC)


def _lead_time_to_time_interval(
    base_datetime: datetime, lead_time_days: int
) -> tuple[str, str]:
    target_date = base_datetime + timedelta(days=lead_time_days)
    time_interval_start = target_date.strftime("%Y-%m-%dT00:00:00Z")
    time_interval_end = target_date.strftime("%Y-%m-%dT23:59:59Z")
    return time_interval_start, time_interval_end
