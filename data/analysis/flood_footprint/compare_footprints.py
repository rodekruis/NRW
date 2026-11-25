"""
Compare today's flood footprint with the footprint from a return period per GloFAS cell
(AB#42674), for the stations that trigger in one archived forecast.

All inputs come from a local clone of the seed repo and from data/data, so it runs without the
NRW API. It writes the comparison tables and figures, and runs the flood forecast.py on the same
inputs to check the whole flow.

Usage (from the data directory):
    uv run python -m analysis.flood_footprint.compare_footprints
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import cast
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
from analysis.flood_footprint.seed_repo_inputs import (
    load_admin_areas,
    load_flood_depth_provider,
    load_population,
    load_stations_and_alert_configs,
)
from dotenv import load_dotenv
from matplotlib.axes import Axes
from pipelines.flood import forecast as flood_forecast
from pipelines.flood.compute_flood_depth import (
    compute_flood_depth,
    determine_cell_return_periods,
    resolve_station_flood_map,
)
from pipelines.flood.constants import (
    GLOFAS_VERSION,
    MINIMUM_FLOOD_DEPTH_METRES,
    MINIMUM_RETURN_PERIOD_YEARS,
    MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES,
)
from pipelines.flood.determine_alerts import (
    determine_temporal_extent,
    ReturnPeriodThresholds,
    ReturnPeriodThresholdValue,
    TimeIntervalReturnPeriodSeverity,
)
from pipelines.flood.determine_exposure import determine_spatial_extent
from pipelines.flood.extract_forecast import (
    determine_peak_lead_time,
    extract_discharge_glofas_station,
    extract_median_discharge,
    TimeIntervalDischarge,
)
from pipelines.flood.footprint_method import (
    regrid_return_period,
    RegriddingMethod,
    ZERO_DEPTH_RETURN_PERIOD,
)
from pipelines.infra.data_provider import DataProvider
from pipelines.infra.data_submitter import DataSubmitter
from pipelines.infra.data_types.admin_area_types import AdminAreasSet
from pipelines.infra.data_types.data_config_types import DataSource, OutputMode
from pipelines.infra.data_types.enums import ForecastSource, HazardType
from pipelines.infra.data_types.flood_depth_provider import FloodDepthProvider
from pipelines.infra.data_types.glofas_return_period_curves import (
    get_glofas_return_period_curves_filename,
    GlofasReturnPeriodCurves,
)
from pipelines.infra.data_types.loaded_data_types import (
    AlertConfig,
    DataType,
    LoadedDataSource,
    RasterData,
)
from pipelines.infra.data_types.location_point import LocationPoint
from pipelines.infra.utils.alert_admin_aggregation import (
    aggregate_to_parent_admin_levels,
)
from pipelines.infra.utils.alert_centroid import compute_alert_centroid
from pipelines.infra.utils.api_client import ApiClient
from pipelines.infra.utils.exposure import (
    aggregate_population_exposed,
    compute_population_exposed,
    create_raster_geometry_clipper,
)
from pipelines.infra.utils.raster import get_raster_extent
from shapely.geometry.base import BaseGeometry
from shared.data_helpers import get_seed_data_repo_path

DATA_DIRECTORY = Path(__file__).parents[2] / "data"
DEFAULT_FORECAST_DIRECTORY = (
    DATA_DIRECTORY / "glofas" / "country_split_alert" / "20260902"
)
DEFAULT_RETURN_PERIOD_CURVES_DIRECTORY = DATA_DIRECTORY / "glofas-return-period-curves"
DEFAULT_FORECAST_OUTPUT_DIRECTORY = DATA_DIRECTORY / "flood-footprint-comparison"
DEFAULT_RESULTS_DIRECTORY = Path(__file__).parent / "results"

MINIMUM_FLOOD_DEPTHS_METRES = (0.0, MINIMUM_FLOOD_DEPTH_METRES)
KILOMETRES_PER_DEGREE = 111.32

TODAY = "today: one flood map for the station"
NEW = "new: return period per cell"
# The same without one of its rules, to show what that rule does.
NEW_SMALL_STREAMS_DRIVE = "new: return period per cell, small streams drive too"
NEW_NO_DRY_FLOOR = "new: return period per cell, no dry floor"
# What CLIMADA does by default: every cell drives, also small streams and near-flat curves.
NEW_ALL_CELLS = "new: return period per cell, all cells drive"

FIGURE_COLUMN_WIDTH_INCHES = 4.2
FIGURE_ROW_HEIGHT_INCHES = 4.4
FIGURE_RESOLUTION_DOTS_PER_INCH = 150
# Depths above this share the darkest colour, so the shallow new footprints stay readable.
FIGURE_MAXIMUM_DEPTH_METRES = 2.0
FIGURE_MAXIMUM_RETURN_PERIOD_YEARS = 5.0
FLOOD_DEPTH_COLOUR_MAP = "viridis_r"
RETURN_PERIOD_COLOUR_MAP = "magma_r"
BOUNDARY_COLOUR = "black"
STATION_COLOUR = "red"
DRIVING_CELL_COLOUR = "white"
DRIVING_CELL_MARKER_SIZE = 9


@dataclass
class Inputs:
    country: str
    admin_level: int
    stations: dict[str, LocationPoint]
    alert_configs: list[AlertConfig]
    admin_areas: AdminAreasSet
    flood_depth_provider: FloodDepthProvider
    population: RasterData
    return_period_curves: GlofasReturnPeriodCurves
    netcdf_paths: list[str]


@dataclass
class CellReturnPeriods:
    """
    Return period per GloFAS cell at one lead time: for the cells that drive the footprint, for
    those plus the small streams, and for all cells.
    """

    driving_cells: RasterData
    driving_cells_and_small_streams: RasterData
    all_cells: RasterData


@dataclass
class FootprintVariant:
    """One way to compute the new footprint, for each of its regridding methods."""

    method: str
    cell_return_periods: RasterData
    regridding_methods: list[RegriddingMethod]
    minimum_return_period: float = MINIMUM_RETURN_PERIOD_YEARS


@dataclass
class TriggeredStation:
    station: LocationPoint
    place_codes: list[str]
    boundary: BaseGeometry
    time_interval_severities: list[TimeIntervalReturnPeriodSeverity]
    peak_lead_time: int


@dataclass
class Footprint:
    station_code: str
    method: str
    regridding: str
    minimum_flood_depth_metres: float
    flood_depth: RasterData


@dataclass
class FootprintColumn:
    """One column of footprints in a figure."""

    method: str
    regridding: str
    minimum_flood_depth_metres: float
    # Replaces the title that names the method, the regridding and the minimum depth.
    title: str | None = None


@dataclass
class ReturnPeriodPanel:
    """One way to get a return period per pixel, and the footprint it gives, for a figure that compares two."""

    label: str
    method: str
    regridding: RegriddingMethod
    cell_return_periods: RasterData


@dataclass
class FootprintMeasure:
    station_code: str
    method: str
    regridding: str
    minimum_flood_depth_metres: float
    flooded_area_square_kilometres: float
    exposed_population: float
    maximum_flood_depth_metres: float


@dataclass
class StationReturnPeriod:
    station_code: str
    peak_lead_time_days: int
    peak_median_discharge: float
    station_return_period: float
    cell_return_period: float
    cell_drives_footprint: bool


def main() -> None:
    arguments = parse_arguments()
    inputs = load_inputs(
        seed_repo_path=get_seed_data_repo_path(),
        country=arguments.country,
        admin_level=arguments.admin_level,
        forecast_directory=arguments.forecast_directory,
        return_period_curves_directory=arguments.return_period_curves_directory,
    )
    station_discharges = extract_station_discharges(inputs)
    peak_lead_times = {
        alert_config.spatial_extent_name: determine_peak_lead_time(
            station_discharges[alert_config.spatial_extent_name],
            alert_config.temporal_extents[0],
        )
        for alert_config in inputs.alert_configs
    }
    cell_return_periods_by_lead_time = {
        lead_time: compute_cell_return_periods(inputs, lead_time)
        for lead_time in sorted(set(peak_lead_times.values()))
    }

    triggered_stations = determine_triggered_stations(
        inputs, station_discharges, peak_lead_times
    )
    footprints = [
        footprint
        for triggered_station in triggered_stations
        for footprint in compute_footprints(
            triggered_station,
            inputs,
            cell_return_periods_by_lead_time[triggered_station.peak_lead_time],
        )
    ]

    results_directory: Path = arguments.results_directory
    results_directory.mkdir(parents=True, exist_ok=True)
    measures = [
        measure_footprint(footprint, triggered_stations, inputs)
        for footprint in footprints
    ]
    station_return_periods = compare_station_and_cell_return_periods(
        inputs, station_discharges, peak_lead_times, cell_return_periods_by_lead_time
    )
    write_rows(measures, results_directory / "footprint_comparison.csv")
    write_rows(
        station_return_periods,
        results_directory / "station_and_cell_return_periods.csv",
    )
    print_summary(measures, station_return_periods)
    for minimum_flood_depth in MINIMUM_FLOOD_DEPTHS_METRES:
        plot_footprints(
            triggered_stations,
            footprints,
            cell_return_periods_by_lead_time,
            columns=[
                FootprintColumn(TODAY, "", minimum_flood_depth),
                FootprintColumn(NEW, RegriddingMethod.NEAREST, minimum_flood_depth),
                FootprintColumn(NEW, RegriddingMethod.BILINEAR, minimum_flood_depth),
            ],
            path=results_directory
            / f"footprint_comparison_minimum_depth_{minimum_flood_depth:g}m.png",
        )
    # Per station, for slides: the steps from today's footprint to the new one.
    for triggered_station in triggered_stations:
        station_code = triggered_station.station.id
        cell_return_periods = cell_return_periods_by_lead_time[
            triggered_station.peak_lead_time
        ]
        plot_footprints(
            [triggered_station],
            footprints,
            cell_return_periods_by_lead_time,
            columns=[
                FootprintColumn(TODAY, "", 0.0, "Today\nthe 10-year flood map"),
                FootprintColumn(
                    NEW_NO_DRY_FLOOR,
                    RegriddingMethod.NEAREST,
                    0.0,
                    "Step 1\ndepth from the return period of each cell",
                ),
                FootprintColumn(
                    NEW,
                    RegriddingMethod.NEAREST,
                    0.0,
                    f"Step 2\ndry below {MINIMUM_RETURN_PERIOD_YEARS:g} years",
                ),
                FootprintColumn(
                    NEW,
                    RegriddingMethod.NEAREST,
                    MINIMUM_FLOOD_DEPTH_METRES,
                    f"Step 3\nat least {MINIMUM_FLOOD_DEPTH_METRES:g} m deep",
                ),
            ],
            path=results_directory / f"footprint_steps_{station_code}.png",
            shows_return_periods=False,
        )
        # Per station, one figure per rule: the footprint with the rule and without it.
        plot_return_periods_and_footprints(
            triggered_station,
            footprints,
            panels=[
                ReturnPeriodPanel(
                    "Small streams drive too",
                    NEW_SMALL_STREAMS_DRIVE,
                    RegriddingMethod.NEAREST,
                    cell_return_periods.driving_cells_and_small_streams,
                ),
                ReturnPeriodPanel(
                    f"Only cells of at least {MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES:g} km² drive",
                    NEW,
                    RegriddingMethod.NEAREST,
                    cell_return_periods.driving_cells,
                ),
            ],
            path=results_directory / f"small_streams_rule_{station_code}.png",
        )
        plot_return_periods_and_footprints(
            triggered_station,
            footprints,
            panels=[
                ReturnPeriodPanel(
                    "Nearest driving cell",
                    NEW,
                    RegriddingMethod.NEAREST,
                    cell_return_periods.driving_cells,
                ),
                ReturnPeriodPanel(
                    "Blend of the four cells around (bilinear)",
                    NEW,
                    RegriddingMethod.BILINEAR,
                    cell_return_periods.driving_cells,
                ),
            ],
            path=results_directory / f"regridding_{station_code}.png",
        )

    run_forecast(inputs, arguments.forecast_output_directory)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", default="MWI")
    parser.add_argument("--admin-level", type=int, default=3)
    parser.add_argument(
        "--forecast-directory", type=Path, default=DEFAULT_FORECAST_DIRECTORY
    )
    parser.add_argument(
        "--return-period-curves-directory",
        type=Path,
        default=DEFAULT_RETURN_PERIOD_CURVES_DIRECTORY,
    )
    parser.add_argument(
        "--results-directory", type=Path, default=DEFAULT_RESULTS_DIRECTORY
    )
    parser.add_argument(
        "--forecast-output-directory",
        type=Path,
        default=DEFAULT_FORECAST_OUTPUT_DIRECTORY,
    )
    return parser.parse_args()


def load_inputs(
    seed_repo_path: Path,
    country: str,
    admin_level: int,
    forecast_directory: Path,
    return_period_curves_directory: Path,
) -> Inputs:
    stations, alert_configs = load_stations_and_alert_configs(
        seed_repo_path, country, admin_level
    )
    netcdf_paths = sorted(
        str(path) for path in forecast_directory.glob(f"dis_*_sliced_{country}.nc")
    )
    if not netcdf_paths:
        raise FileNotFoundError(f"No {country} forecast files in {forecast_directory}")

    return Inputs(
        country=country,
        admin_level=admin_level,
        stations=stations,
        alert_configs=alert_configs,
        admin_areas=load_admin_areas(seed_repo_path, country, admin_level),
        flood_depth_provider=load_flood_depth_provider(seed_repo_path, country),
        population=load_population(seed_repo_path, country),
        return_period_curves=GlofasReturnPeriodCurves.from_geotiff(
            (
                return_period_curves_directory
                / get_glofas_return_period_curves_filename(country, GLOFAS_VERSION)
            ).read_bytes()
        ),
        netcdf_paths=netcdf_paths,
    )


def extract_station_discharges(
    inputs: Inputs,
) -> dict[str, list[TimeIntervalDischarge]]:
    station_discharges: dict[str, list[TimeIntervalDischarge]] = {}
    for alert_config in inputs.alert_configs:
        station = inputs.stations[alert_config.spatial_extent_name]
        station_discharges.update(
            extract_discharge_glofas_station(
                station_code=station.id,
                station=station,
                netcdf_paths=inputs.netcdf_paths,
                temporal_extent=alert_config.temporal_extents[0],
            )
        )
    return station_discharges


def compute_cell_return_periods(inputs: Inputs, lead_time: int) -> CellReturnPeriods:
    median_discharge = extract_median_discharge(inputs.netcdf_paths, lead_time)
    maximum_return_period = max(inputs.flood_depth_provider.available_return_periods)
    driving_cells = determine_cell_return_periods(
        median_discharge, inputs.return_period_curves, maximum_return_period
    )
    driving_cells_and_small_streams = determine_cell_return_periods(
        median_discharge,
        inputs.return_period_curves,
        maximum_return_period,
        minimum_upstream_area=0.0,
    )
    all_cells = determine_cell_return_periods(
        median_discharge,
        inputs.return_period_curves,
        maximum_return_period,
        minimum_upstream_area=0.0,
        minimum_gumbel_scale=0.0,
    )
    if (
        driving_cells is None
        or driving_cells_and_small_streams is None
        or all_cells is None
    ):
        raise RuntimeError(
            "The forecast is not on the grid of the return period curves"
        )
    return CellReturnPeriods(
        driving_cells=driving_cells,
        driving_cells_and_small_streams=driving_cells_and_small_streams,
        all_cells=all_cells,
    )


def determine_triggered_stations(
    inputs: Inputs,
    station_discharges: dict[str, list[TimeIntervalDischarge]],
    peak_lead_times: dict[str, int],
) -> list[TriggeredStation]:
    thresholds = _get_station_thresholds(inputs.stations)
    triggered_stations: list[TriggeredStation] = []
    for alert_config in inputs.alert_configs:
        station = inputs.stations[alert_config.spatial_extent_name]
        time_interval_severities = determine_temporal_extent(
            station_code=station.id,
            time_interval_discharges=station_discharges[station.id],
            thresholds=thresholds,
        )
        boundary, place_codes = determine_spatial_extent(
            alert_config.spatial_extent_place_codes, inputs.admin_areas
        )
        if time_interval_severities and boundary is not None:
            triggered_stations.append(
                TriggeredStation(
                    station,
                    place_codes,
                    boundary,
                    time_interval_severities,
                    peak_lead_times[station.id],
                )
            )
    return triggered_stations


def compute_footprints(
    triggered_station: TriggeredStation,
    inputs: Inputs,
    cell_return_periods: CellReturnPeriods,
) -> list[Footprint]:
    station_code = triggered_station.station.id
    variants = [
        FootprintVariant(
            NEW, cell_return_periods.driving_cells, list(RegriddingMethod)
        ),
        FootprintVariant(
            NEW_SMALL_STREAMS_DRIVE,
            cell_return_periods.driving_cells_and_small_streams,
            [RegriddingMethod.NEAREST],
        ),
        FootprintVariant(
            NEW_NO_DRY_FLOOR,
            cell_return_periods.driving_cells,
            [RegriddingMethod.NEAREST],
            minimum_return_period=ZERO_DEPTH_RETURN_PERIOD,
        ),
        FootprintVariant(
            NEW_ALL_CELLS, cell_return_periods.all_cells, [RegriddingMethod.BILINEAR]
        ),
    ]
    footprints: list[Footprint] = []
    for minimum_flood_depth in MINIMUM_FLOOD_DEPTHS_METRES:
        footprints.append(
            Footprint(
                station_code,
                TODAY,
                "",
                minimum_flood_depth,
                compute_todays_flood_depth(
                    triggered_station, inputs, minimum_flood_depth
                ),
            )
        )
        for variant in variants:
            for regridding_method in variant.regridding_methods:
                flood_depth = compute_flood_depth(
                    time_interval_severities=triggered_station.time_interval_severities,
                    cell_return_periods=variant.cell_return_periods,
                    boundary=triggered_station.boundary,
                    flood_depth_provider=inputs.flood_depth_provider,
                    regridding_method=regridding_method,
                    minimum_flood_depth=minimum_flood_depth,
                    minimum_return_period=variant.minimum_return_period,
                )
                if flood_depth is None:
                    raise RuntimeError(
                        f"The flood maps do not cover station {station_code}"
                    )
                footprints.append(
                    Footprint(
                        station_code,
                        variant.method,
                        regridding_method,
                        minimum_flood_depth,
                        flood_depth,
                    )
                )
    return footprints


def compute_todays_flood_depth(
    triggered_station: TriggeredStation, inputs: Inputs, minimum_flood_depth: float
) -> RasterData:
    """Today's footprint: the one flood map for the station's return period, clipped to its area."""
    station_flood_map = resolve_station_flood_map(
        triggered_station.time_interval_severities, inputs.flood_depth_provider
    )
    flood_depth = create_raster_geometry_clipper(
        triggered_station.boundary, station_flood_map
    ).clip(station_flood_map)
    flood_depth.array[flood_depth.array < minimum_flood_depth] = 0.0
    return flood_depth


def measure_footprint(
    footprint: Footprint, triggered_stations: list[TriggeredStation], inputs: Inputs
) -> FootprintMeasure:
    triggered_station = next(
        triggered_station
        for triggered_station in triggered_stations
        if triggered_station.station.id == footprint.station_code
    )
    population_exposed_raster = compute_population_exposed(
        inputs.population, footprint.flood_depth
    )
    population_exposed = (
        aggregate_population_exposed(
            population_exposed_raster,
            triggered_station.place_codes,
            inputs.admin_areas,
        )
        if population_exposed_raster is not None
        else {}
    )
    return FootprintMeasure(
        station_code=footprint.station_code,
        method=footprint.method,
        regridding=footprint.regridding,
        minimum_flood_depth_metres=footprint.minimum_flood_depth_metres,
        flooded_area_square_kilometres=round(
            _measure_flooded_area(footprint.flood_depth), 2
        ),
        exposed_population=sum(population_exposed.values()),
        maximum_flood_depth_metres=round(float(footprint.flood_depth.array.max()), 2),
    )


def compare_station_and_cell_return_periods(
    inputs: Inputs,
    station_discharges: dict[str, list[TimeIntervalDischarge]],
    peak_lead_times: dict[str, int],
    cell_return_periods_by_lead_time: dict[int, CellReturnPeriods],
) -> list[StationReturnPeriod]:
    """The station's return period comes from stepwise thresholds, its cell's from the continuous curve."""
    thresholds = _get_station_thresholds(inputs.stations)
    comparisons: list[StationReturnPeriod] = []
    for alert_config in inputs.alert_configs:
        station = inputs.stations[alert_config.spatial_extent_name]
        discharges = station_discharges[station.id]
        time_interval_severities = determine_temporal_extent(
            station.id, discharges, thresholds
        )
        cell_return_periods = cell_return_periods_by_lead_time[
            peak_lead_times[station.id]
        ]
        transform = cell_return_periods.all_cells.transform
        row = int((station.lat - transform.f) // transform.e)
        column = int((station.lon - transform.c) // transform.a)
        comparisons.append(
            StationReturnPeriod(
                station_code=station.id,
                peak_lead_time_days=peak_lead_times[station.id],
                peak_median_discharge=round(
                    max(
                        float(np.nanmedian(discharge.ensemble_discharges))
                        for discharge in discharges
                    ),
                    1,
                ),
                station_return_period=max(
                    (
                        severity.median_return_period
                        for severity in time_interval_severities
                    ),
                    default=0.0,
                ),
                cell_return_period=round(
                    float(cell_return_periods.all_cells.array[row, column]), 3
                ),
                cell_drives_footprint=bool(
                    np.isfinite(cell_return_periods.driving_cells.array[row, column])
                ),
            )
        )
    return comparisons


def plot_footprints(
    triggered_stations: list[TriggeredStation],
    footprints: list[Footprint],
    cell_return_periods_by_lead_time: dict[int, CellReturnPeriods],
    columns: list[FootprintColumn],
    path: Path,
    shows_return_periods: bool = True,
) -> None:
    """One row per station: a footprint per column, then the return periods that drive the new footprints."""
    column_count = len(columns) + (1 if shows_return_periods else 0)
    figure, axes = plt.subplots(
        len(triggered_stations),
        column_count,
        figsize=(
            FIGURE_COLUMN_WIDTH_INCHES * column_count,
            FIGURE_ROW_HEIGHT_INCHES * len(triggered_stations),
        ),
        squeeze=False,
        constrained_layout=True,
    )
    depth_image = None
    return_period_image = None
    for row, triggered_station in enumerate(triggered_stations):
        station = triggered_station.station
        station_return_period = max(
            severity.median_return_period
            for severity in triggered_station.time_interval_severities
        )
        for column, footprint_column in enumerate(columns):
            footprint = _find_footprint(
                footprints,
                station.id,
                footprint_column.method,
                footprint_column.regridding,
                footprint_column.minimum_flood_depth_metres,
            )
            depth_image = _plot_raster(
                axes[row][column],
                footprint.flood_depth.array,
                footprint.flood_depth,
                FLOOD_DEPTH_COLOUR_MAP,
                FIGURE_MAXIMUM_DEPTH_METRES,
            )
            _plot_area(axes[row][column], triggered_station)
            axes[row][column].set_title(
                footprint_column.title
                or (
                    f"{station.id} at {station_return_period:g} years\n{footprint.method}"
                    + (f", {footprint.regridding}" if footprint.regridding else "")
                    + f"\ndepth of at least {footprint.minimum_flood_depth_metres:g} m"
                ),
                fontsize="small",
            )

        if not shows_return_periods:
            continue
        flood_depth = footprint.flood_depth
        return_period_image = _plot_raster(
            axes[row][-1],
            _regrid_to_footprint(
                cell_return_periods_by_lead_time[
                    triggered_station.peak_lead_time
                ].driving_cells,
                flood_depth,
                RegriddingMethod.NEAREST,
            ),
            flood_depth,
            RETURN_PERIOD_COLOUR_MAP,
            FIGURE_MAXIMUM_RETURN_PERIOD_YEARS,
        )
        _plot_area(axes[row][-1], triggered_station)
        axes[row][-1].set_title(
            f"{station.id}, lead time {triggered_station.peak_lead_time} days\n"
            "return period of the nearest driving cell\n",
            fontsize="small",
        )

    if depth_image is not None:
        figure.colorbar(
            depth_image,
            ax=axes[:, : len(columns)],
            location="bottom",
            shrink=0.4,
            extend="max",
            label="Flood depth (m)",
        )
    if return_period_image is not None:
        figure.colorbar(
            return_period_image,
            ax=axes[:, -1],
            location="bottom",
            shrink=0.9,
            extend="max",
            label="Return period (years)",
        )
    figure.savefig(path, dpi=FIGURE_RESOLUTION_DOTS_PER_INCH)
    plt.close(figure)
    print(f"Wrote {path}")


def plot_return_periods_and_footprints(
    triggered_station: TriggeredStation,
    footprints: list[Footprint],
    panels: list[ReturnPeriodPanel],
    path: Path,
) -> None:
    """
    Compare two ways to get a return period per pixel. Left: the return period per pixel of each,
    with a dot on every cell that drives. Right: the footprints they give, at the minimum depth.
    """
    station = triggered_station.station
    figure, axes = plt.subplots(
        1,
        2 * len(panels),
        figsize=(
            FIGURE_COLUMN_WIDTH_INCHES * 2 * len(panels),
            FIGURE_ROW_HEIGHT_INCHES,
        ),
        constrained_layout=True,
    )
    depth_image = None
    return_period_image = None
    for column, panel in enumerate(panels):
        footprint = _find_footprint(
            footprints,
            station.id,
            panel.method,
            panel.regridding,
            MINIMUM_FLOOD_DEPTH_METRES,
        )
        return_period_axis = axes[column]
        footprint_axis = axes[column + len(panels)]
        return_period_image = _plot_raster(
            return_period_axis,
            _regrid_to_footprint(
                panel.cell_return_periods, footprint.flood_depth, panel.regridding
            ),
            footprint.flood_depth,
            RETURN_PERIOD_COLOUR_MAP,
            FIGURE_MAXIMUM_RETURN_PERIOD_YEARS,
        )
        _plot_driving_cells(
            return_period_axis, panel.cell_return_periods, footprint.flood_depth
        )
        return_period_axis.set_title(
            f"{panel.label}\nreturn period per pixel", fontsize="small"
        )
        depth_image = _plot_raster(
            footprint_axis,
            footprint.flood_depth.array,
            footprint.flood_depth,
            FLOOD_DEPTH_COLOUR_MAP,
            FIGURE_MAXIMUM_DEPTH_METRES,
        )
        footprint_axis.set_title(
            f"{panel.label}\nfootprint, depth of at least {MINIMUM_FLOOD_DEPTH_METRES:g} m",
            fontsize="small",
        )
        for axis in (return_period_axis, footprint_axis):
            _plot_area(axis, triggered_station)

    if depth_image is not None and return_period_image is not None:
        figure.colorbar(
            return_period_image,
            ax=axes[: len(panels)],
            location="bottom",
            shrink=0.5,
            extend="max",
            label="Return period (years); dots are the cells that drive",
        )
        figure.colorbar(
            depth_image,
            ax=axes[len(panels) :],
            location="bottom",
            shrink=0.5,
            extend="max",
            label="Flood depth (m)",
        )
    figure.savefig(path, dpi=FIGURE_RESOLUTION_DOTS_PER_INCH)
    plt.close(figure)
    print(f"Wrote {path}")


def run_forecast(inputs: Inputs, output_directory: Path) -> None:
    """Run the flood forecast.py on the same inputs and write its forecast.json, without the NRW API."""
    load_dotenv()
    api_client = ApiClient()
    data_provider = DataProvider(api_client, local_data="country")
    for data_source, data_type, data in (
        (
            DataSource.ALERT_CONFIGS_NRW_API,
            DataType.ALERT_CONFIG_LIST,
            inputs.alert_configs,
        ),
        (
            DataSource.GLOFAS_STATIONS_NRW_API,
            DataType.LOCATION_POINT_DICT,
            inputs.stations,
        ),
        (DataSource.ADMIN_AREA_NRW_API, DataType.ADMIN_AREA_SET, inputs.admin_areas),
        (
            DataSource.FLOOD_DEPTH_SEED_REPO,
            DataType.FLOOD_DEPTH_PROVIDER,
            inputs.flood_depth_provider,
        ),
        (
            DataSource.GLOFAS_RETURN_PERIOD_CURVES_SEED_REPO,
            DataType.GLOFAS_RETURN_PERIOD_CURVES,
            inputs.return_period_curves,
        ),
        (DataSource.POPULATION_NRW_API, DataType.RASTER_DATA, inputs.population),
        (DataSource.GLOFAS_DISCHARGE_FTP, DataType.PATH_LIST, inputs.netcdf_paths),
    ):
        data_provider.loaded_data[data_source] = LoadedDataSource(
            data_type=data_type, data_source=data_source, data=data
        )

    data_submitter = DataSubmitter(api_client)
    data_submitter.set_forecast_metadata(
        issued_at=datetime.now(UTC),
        hazard_type=HazardType.FLOODS,
        forecast_sources=[ForecastSource.GLOFAS_RIVER_DISCHARGE],
        country_code_iso3=inputs.country,
    )
    # The forecast files already are the archived ones.
    with patch.object(flood_forecast, "archive_alert_glofas_files"):
        flood_forecast.calculate_flood_forecasts(
            data_provider, data_submitter, inputs.country, inputs.admin_level
        )
    for alert in data_submitter.get_alerts():
        alert.centroid = compute_alert_centroid(alert, inputs.admin_areas)
        aggregate_to_parent_admin_levels(alert, inputs.admin_areas)

    errors = data_submitter.send_all(OutputMode.LOCAL, str(output_directory))
    if errors:
        raise RuntimeError(f"forecast.py failed: {errors}")
    print(
        f"forecast.py created alerts {[alert.event_name for alert in data_submitter.get_alerts()]}; "
        f"wrote {output_directory / 'forecast.json'}"
    )


def print_summary(
    measures: list[FootprintMeasure], station_return_periods: list[StationReturnPeriod]
) -> None:
    for measure in measures:
        print(
            f"{measure.station_code}, at least {measure.minimum_flood_depth_metres:g} m, "
            f"{measure.method}{', ' + measure.regridding if measure.regridding else ''}: "
            f"{measure.flooded_area_square_kilometres:.1f} km2 flooded, "
            f"{measure.exposed_population:.0f} people exposed, "
            f"up to {measure.maximum_flood_depth_metres:.2f} m deep"
        )
    for station_return_period in station_return_periods:
        print(
            f"{station_return_period.station_code}, peak at lead time "
            f"{station_return_period.peak_lead_time_days} days with "
            f"{station_return_period.peak_median_discharge:.0f} m3/s: station at "
            f"{station_return_period.station_return_period:g} years, its cell at "
            f"{station_return_period.cell_return_period:.2f} years"
            + (
                ""
                if station_return_period.cell_drives_footprint
                else " (does not drive)"
            )
        )


def write_rows(
    rows: list[FootprintMeasure] | list[StationReturnPeriod], path: Path
) -> None:
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(asdict(rows[0])))
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
    print(f"Wrote {path}")


def _get_station_thresholds(
    stations: dict[str, LocationPoint],
) -> list[ReturnPeriodThresholds]:
    return [
        {
            "station_code": station.id,
            "thresholds": cast(
                list[ReturnPeriodThresholdValue], station.attributes["thresholds"]
            ),
        }
        for station in stations.values()
    ]


def _measure_flooded_area(flood_depth: RasterData) -> float:
    transform = flood_depth.transform
    row_count = flood_depth.array.shape[0]
    latitudes = transform.f + (np.arange(row_count) + 0.5) * transform.e
    pixel_areas = (
        abs(transform.a * transform.e)
        * KILOMETRES_PER_DEGREE**2
        * np.cos(np.radians(latitudes))
    )
    is_flooded = (flood_depth.array > 0) & (flood_depth.array != flood_depth.nodata)
    return float((is_flooded.sum(axis=1) * pixel_areas).sum())


def _find_footprint(
    footprints: list[Footprint],
    station_code: str,
    method: str,
    regridding: str,
    minimum_flood_depth: float,
) -> Footprint:
    return next(
        footprint
        for footprint in footprints
        if footprint.station_code == station_code
        and footprint.method == method
        and footprint.regridding == regridding
        and footprint.minimum_flood_depth_metres == minimum_flood_depth
    )


def _regrid_to_footprint(
    cell_return_periods: RasterData,
    flood_depth: RasterData,
    regridding_method: RegriddingMethod,
) -> np.ndarray:
    """The return period per pixel of a footprint."""
    return regrid_return_period(
        cell_return_periods.array,
        cell_return_periods.transform,
        flood_depth.transform,
        cast(tuple[int, int], flood_depth.array.shape),
        regridding_method,
    )


def _plot_driving_cells(
    axes: Axes, cell_return_periods: RasterData, grid: RasterData
) -> None:
    """A dot on the centre of every cell that drives, inside the extent of the grid."""
    transform = cell_return_periods.transform
    rows, columns = np.nonzero(np.isfinite(cell_return_periods.array))
    longitudes = transform.c + (columns + 0.5) * transform.a
    latitudes = transform.f + (rows + 0.5) * transform.e
    extent = get_raster_extent(grid)
    is_inside = (
        (longitudes >= extent["xmin"])
        & (longitudes <= extent["xmax"])
        & (latitudes >= extent["ymin"])
        & (latitudes <= extent["ymax"])
    )
    axes.scatter(
        longitudes[is_inside],
        latitudes[is_inside],
        s=DRIVING_CELL_MARKER_SIZE,
        color=DRIVING_CELL_COLOUR,
        linewidths=0,
    )


def _plot_raster(
    axes: Axes,
    values: np.ndarray,
    grid: RasterData,
    colour_map: str,
    maximum_value: float,
):
    extent = get_raster_extent(grid)
    return axes.imshow(
        np.ma.masked_where(~(values > 0), values),
        extent=(extent["xmin"], extent["xmax"], extent["ymin"], extent["ymax"]),
        cmap=colour_map,
        vmin=0,
        vmax=maximum_value,
        interpolation="nearest",
    )


def _plot_area(axes: Axes, triggered_station: TriggeredStation) -> None:
    boundary = triggered_station.boundary
    for polygon in getattr(boundary, "geoms", [boundary]):
        axes.plot(*polygon.exterior.xy, color=BOUNDARY_COLOUR, linewidth=0.6)
    axes.plot(
        triggered_station.station.lon,
        triggered_station.station.lat,
        marker="^",
        color=STATION_COLOUR,
        markersize=6,
        linestyle="none",
    )
    axes.tick_params(labelsize="x-small")


if __name__ == "__main__":
    main()
