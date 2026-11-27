"""
How much the results depend on the three values of the flood footprint that are not agreed
(AB#42674): the minimum flood depth, the minimum upstream area and the minimum curve scale.

The first two are tested on the archived forecast that compare_footprints.py uses. The curve
scale has no effect there, so it is tested on the curves of all countries and on one global
forecast: per large-river cell, the highest return period over the lead times of one ensemble
member. The script also counts the stations whose footprint can be empty at a low alert level,
and draws from which river size the flood maps hold floods.

Usage (from the data directory):
    uv run python -m analysis.flood_footprint.check_sensitivity
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass, replace
from itertools import pairwise
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import xarray as xr
from analysis.flood_footprint.compare_footprints import (
    DATA_DIRECTORY,
    DEFAULT_FORECAST_DIRECTORY,
    DEFAULT_RESULTS_DIRECTORY,
    DEFAULT_RETURN_PERIOD_CURVES_DIRECTORY,
    determine_triggered_stations,
    extract_station_discharges,
    Footprint,
    Inputs,
    load_inputs,
    measure_footprint,
    NEW,
    TriggeredStation,
)
from analysis.flood_footprint.plot_open_decisions import (
    ALL_COUNTRIES,
    count_pixels_per_cell,
    find_country_cells,
)
from analysis.flood_footprint.seed_repo_inputs import (
    FLOOD_LEAD_TIME_SPECTRUM,
    load_admin_areas,
    load_flood_depth_provider,
    load_stations_and_alert_configs,
)
from matplotlib.ticker import PercentFormatter
from pipelines.flood.compute_flood_depth import (
    compute_flood_depth,
    determine_cell_return_periods,
)
from pipelines.flood.constants import (
    GLOFAS_VERSION,
    MINIMUM_FLOOD_DEPTH_METRES,
    MINIMUM_RETURN_PERIOD_YEARS,
    MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES,
    REGRIDDING_METHOD,
)
from pipelines.flood.determine_exposure import determine_spatial_extent
from pipelines.flood.extract_forecast import (
    determine_peak_lead_time,
    extract_median_discharge,
)
from pipelines.flood.footprint_method import (
    compute_return_period,
    ZERO_DEPTH_RETURN_PERIOD,
)
from pipelines.infra.config_reader import ConfigReader
from pipelines.infra.data_types.glofas_return_period_curves import (
    get_glofas_return_period_curves_filename,
    GlofasReturnPeriodCurves,
)
from pipelines.infra.data_types.loaded_data_types import RasterData
from pipelines.infra.utils.exposure import create_raster_geometry_clipper
from rasterio.features import geometry_mask
from scipy.ndimage import maximum_filter
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union
from shared.data_helpers import get_seed_data_repo_path, target_countries_iso_a3

DEFAULT_GLOBAL_FORECAST_PATH = (
    DATA_DIRECTORY / "glofas" / "raw" / "20261029" / "dis_00_2026102900.nc"
)

MINIMUM_FLOOD_DEPTHS_METRES = (0.0, 0.1, 0.2, 0.3, 0.5)
# The forecast discharge of every cell is multiplied by these, to mimic a larger flood.
DISCHARGE_FACTORS = (1.0, 1.35, 1.55, 1.85)
MINIMUM_UPSTREAM_AREAS_SQUARE_KILOMETRES = (0.0, 100.0, 250.0, 500.0, 1000.0, 2000.0)
# Bounds of the classes of upstream area (km²) in which the cells with flooding are counted.
UPSTREAM_AREA_CLASS_WIDTH = 100
UPSTREAM_AREA_CLASS_BOUNDS = tuple(range(0, 1501, UPSTREAM_AREA_CLASS_WIDTH))
# GloFAS shows its own forecast products for rivers from this upstream area, since version 4.
GLOFAS_PRODUCTS_MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES = 250.0

FIGURE_RESOLUTION_DOTS_PER_INCH = 150
BELOW_MINIMUM_COLOUR = "#c9ccd1"
ABOVE_MINIMUM_COLOUR = "#1b6ca8"
MINIMUM_LINE_COLOUR = "black"
GLOFAS_PRODUCTS_LINE_COLOUR = "#d1495b"
MINIMUM_GUMBEL_SCALES_CUBIC_METRES_PER_SECOND = (0.1, 1.0, 5.0)
# A large-river cell above this return period in a forecast is either in an extreme flood or on
# a curve that is too flat to trust.
HIGH_RETURN_PERIOD = 100.0
# Return periods below the lowest flood map at which a footprint can come out empty.
LOW_ALERT_RETURN_PERIODS = (1.5, 2.0, 5.0)
FLOODS_CONFIG_PATH = (
    Path(__file__).parents[2] / "pipelines" / "infra" / "configs" / "floods.yaml"
)

SQUARE_METRES_PER_SQUARE_KILOMETRE = 1_000_000.0
SHARE_DECIMALS = 4
DISCHARGE_DECIMALS = 3
# A cell and the eight cells around it.
ADJACENT_CELLS_WINDOW = 3
WHOLE_COUNTRY = "whole country"
ALERT_AREAS = "alert areas"
DISCHARGE_VARIABLE = "dis"
LATITUDE = "lat"
LONGITUDE = "lon"
# Coordinates of the forecast and the curves may differ this much, in degrees.
COORDINATE_TOLERANCE_DEGREES = 1e-3


@dataclass
class FloodDepthSensitivity:
    station_code: str
    discharge_factor: float
    station_cell_return_period: float
    minimum_flood_depth_metres: float
    exposed_population: float


@dataclass
class UpstreamAreaSensitivity:
    station_code: str
    minimum_upstream_area_square_kilometres: float
    exposed_population: float


@dataclass
class FloodMapPixels:
    """Per GloFAS cell of a country: the wet pixels and all pixels of its widest flood map."""

    flood_map_return_period: int
    wet_pixels_per_cell: np.ndarray
    pixels_per_cell: np.ndarray


@dataclass
class DrivingCellDistance:
    """
    Where the wet pixels of the widest flood maps lie when cells drive from one minimum upstream
    area: in a cell that drives, in a cell next to one, or farther away. For all countries
    together.
    """

    minimum_upstream_area_square_kilometres: float
    wet_pixels: int
    share_in_driving_cells: float
    share_next_to_driving_cells: float
    share_farther_away: float


@dataclass
class FloodedCells:
    """Cells of one class of upstream area, and how many of them have flooding in the widest flood map."""

    country: str
    flood_map_return_period: int
    minimum_upstream_area_square_kilometres: int
    maximum_upstream_area_square_kilometres: int
    cells: int
    cells_with_flooding: int
    share_with_flooding: float


@dataclass
class GumbelScaleSensitivity:
    """
    What a minimum curve scale switches off, among the large-river cells of a country or of the
    areas of its alerts. And, in one forecast, how many of the cells that would flood a
    footprint and of the cells above the high return period it switches off, and the highest
    discharge among the latter: without water, their return period is false.
    """

    country: str
    area: str
    minimum_scale: float
    large_river_cells: int
    cells_not_driving: int
    share_not_driving: float
    cells_at_minimum_return_period_not_driving: int
    cells_above_high_return_period: int
    cells_above_high_return_period_not_driving: int
    highest_discharge_of_those_cells: float


@dataclass
class ForecastCells:
    """Per large-river cell: its curve scale, and its peak discharge and return period in one forecast."""

    scale: np.ndarray
    peak_discharge: np.ndarray
    peak_return_period: np.ndarray


@dataclass
class PossibleEmptyFootprints:
    """
    Stations whose footprint comes out empty when every cell in their area is at one return
    period, among the stations whose area the flood maps cover.
    """

    return_period: float
    minimum_flood_depth_metres: float
    stations: int
    stations_outside_flood_maps: int
    stations_with_empty_footprint: int
    station_codes_with_empty_footprint: str


def main() -> None:
    arguments = parse_arguments()
    seed_repo_path = get_seed_data_repo_path()
    results_directory: Path = arguments.results_directory
    results_directory.mkdir(parents=True, exist_ok=True)

    inputs = load_inputs(
        seed_repo_path=seed_repo_path,
        country=arguments.country,
        admin_level=arguments.admin_level,
        forecast_directory=arguments.forecast_directory,
        return_period_curves_directory=arguments.return_period_curves_directory,
    )
    station_discharges = extract_station_discharges(inputs)
    triggered_stations = determine_triggered_stations(
        inputs,
        station_discharges,
        peak_lead_times={
            alert_config.spatial_extent_name: determine_peak_lead_time(
                station_discharges[alert_config.spatial_extent_name],
                alert_config.temporal_extents[0],
            )
            for alert_config in inputs.alert_configs
        },
    )
    write_rows(
        check_flood_depth_sensitivity(inputs, triggered_stations),
        results_directory / "sensitivity_minimum_flood_depth.csv",
    )
    write_rows(
        check_upstream_area_sensitivity(inputs, triggered_stations),
        results_directory / "sensitivity_minimum_upstream_area.csv",
    )

    curves_by_country = {
        country: GlofasReturnPeriodCurves.from_geotiff(
            (
                arguments.return_period_curves_directory
                / get_glofas_return_period_curves_filename(country, GLOFAS_VERSION)
            ).read_bytes()
        )
        for country in arguments.countries
    }
    flood_map_pixels_by_country = count_flood_map_pixels(
        seed_repo_path, curves_by_country
    )
    flooded_cells = count_flooded_cells(curves_by_country, flood_map_pixels_by_country)
    write_rows(flooded_cells, results_directory / "flooded_cells_by_upstream_area.csv")
    plot_flooded_cells(
        flooded_cells, results_directory / "flooded_cells_by_upstream_area.png"
    )
    write_rows(
        check_driving_cell_distance(curves_by_country, flood_map_pixels_by_country),
        results_directory / "flood_map_wet_pixels_by_minimum_upstream_area.csv",
    )
    alert_areas_by_country = {
        country: load_alert_areas(seed_repo_path, country, admin_level)
        for country, admin_level in load_target_admin_levels().items()
        if country in curves_by_country
    }
    write_rows(
        check_gumbel_scale_sensitivity(
            seed_repo_path,
            curves_by_country,
            alert_areas_by_country,
            arguments.global_forecast_path,
        ),
        results_directory / "sensitivity_minimum_gumbel_scale.csv",
    )
    write_rows(
        count_possible_empty_footprints(seed_repo_path, alert_areas_by_country),
        results_directory / "possible_empty_footprints.csv",
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--country", default="MWI")
    parser.add_argument("--admin-level", type=int, default=3)
    parser.add_argument(
        "--forecast-directory", type=Path, default=DEFAULT_FORECAST_DIRECTORY
    )
    parser.add_argument(
        "--countries",
        nargs="+",
        default=sorted(target_countries_iso_a3),
        help="For the upstream area classes and the curve scale",
    )
    parser.add_argument(
        "--global-forecast-path",
        type=Path,
        default=DEFAULT_GLOBAL_FORECAST_PATH,
        help="One ensemble member of a global GloFAS forecast, for the curve scale",
    )
    parser.add_argument(
        "--return-period-curves-directory",
        type=Path,
        default=DEFAULT_RETURN_PERIOD_CURVES_DIRECTORY,
    )
    parser.add_argument(
        "--results-directory", type=Path, default=DEFAULT_RESULTS_DIRECTORY
    )
    return parser.parse_args()


def check_flood_depth_sensitivity(
    inputs: Inputs, triggered_stations: list[TriggeredStation]
) -> list[FloodDepthSensitivity]:
    """Exposed population per minimum flood depth, for the forecast as it is and for larger floods."""
    maximum_return_period = max(inputs.flood_depth_provider.available_return_periods)
    sensitivities: list[FloodDepthSensitivity] = []
    for triggered_station in triggered_stations:
        median_discharge = _extract_median_discharge(inputs, triggered_station)
        for discharge_factor in DISCHARGE_FACTORS:
            cell_return_periods = determine_cell_return_periods(
                replace(
                    median_discharge, array=median_discharge.array * discharge_factor
                ),
                inputs.return_period_curves,
                maximum_return_period,
            )
            if cell_return_periods is None:
                raise RuntimeError(
                    "The forecast is not on the grid of the return period curves"
                )
            for minimum_flood_depth in MINIMUM_FLOOD_DEPTHS_METRES:
                sensitivities.append(
                    FloodDepthSensitivity(
                        station_code=triggered_station.station.id,
                        discharge_factor=discharge_factor,
                        station_cell_return_period=_get_station_cell_return_period(
                            cell_return_periods, triggered_station
                        ),
                        minimum_flood_depth_metres=minimum_flood_depth,
                        exposed_population=_measure_exposed_population(
                            inputs,
                            triggered_station,
                            triggered_stations,
                            cell_return_periods,
                            minimum_flood_depth,
                        ),
                    )
                )
    for sensitivity in sensitivities:
        print(
            f"{sensitivity.station_code}, discharge x{sensitivity.discharge_factor:g} "
            f"({sensitivity.station_cell_return_period:.1f} years at the station), at least "
            f"{sensitivity.minimum_flood_depth_metres:g} m: "
            f"{sensitivity.exposed_population:.0f} people exposed"
        )
    return sensitivities


def check_upstream_area_sensitivity(
    inputs: Inputs, triggered_stations: list[TriggeredStation]
) -> list[UpstreamAreaSensitivity]:
    """Exposed population per minimum upstream area of the cells that drive the footprint."""
    maximum_return_period = max(inputs.flood_depth_provider.available_return_periods)
    sensitivities: list[UpstreamAreaSensitivity] = []
    for triggered_station in triggered_stations:
        median_discharge = _extract_median_discharge(inputs, triggered_station)
        for minimum_upstream_area in MINIMUM_UPSTREAM_AREAS_SQUARE_KILOMETRES:
            cell_return_periods = determine_cell_return_periods(
                median_discharge,
                inputs.return_period_curves,
                maximum_return_period,
                minimum_upstream_area=minimum_upstream_area,
            )
            if cell_return_periods is None:
                raise RuntimeError(
                    "The forecast is not on the grid of the return period curves"
                )
            sensitivities.append(
                UpstreamAreaSensitivity(
                    station_code=triggered_station.station.id,
                    minimum_upstream_area_square_kilometres=minimum_upstream_area,
                    exposed_population=_measure_exposed_population(
                        inputs,
                        triggered_station,
                        triggered_stations,
                        cell_return_periods,
                        MINIMUM_FLOOD_DEPTH_METRES,
                    ),
                )
            )
    for sensitivity in sensitivities:
        print(
            f"{sensitivity.station_code}, cells of at least "
            f"{sensitivity.minimum_upstream_area_square_kilometres:g} km2 drive: "
            f"{sensitivity.exposed_population:.0f} people exposed"
        )
    return sensitivities


def count_flood_map_pixels(
    seed_repo_path: Path, curves_by_country: dict[str, GlofasReturnPeriodCurves]
) -> dict[str, FloodMapPixels]:
    flood_map_pixels_by_country: dict[str, FloodMapPixels] = {}
    for country, curves in curves_by_country.items():
        flood_depth_provider = load_flood_depth_provider(seed_repo_path, country)
        return_period = max(flood_depth_provider.available_return_periods)
        wet_pixels_per_cell, pixels_per_cell = count_pixels_per_cell(
            flood_depth_provider.get_raster(return_period), curves
        )
        flood_map_pixels_by_country[country] = FloodMapPixels(
            return_period, wet_pixels_per_cell, pixels_per_cell
        )
    return flood_map_pixels_by_country


def check_driving_cell_distance(
    curves_by_country: dict[str, GlofasReturnPeriodCurves],
    flood_map_pixels_by_country: dict[str, FloodMapPixels],
) -> list[DrivingCellDistance]:
    """
    Per minimum upstream area, where the flooding in the flood maps lies relative to the cells
    that drive. Pixels in a cell that does not drive take the nearest cell that does: next door
    that is mostly the river whose floodplain they are on, farther away it is a guess. So the
    share farther away is what a higher minimum costs.
    """
    distances: list[DrivingCellDistance] = []
    for minimum_upstream_area in MINIMUM_UPSTREAM_AREAS_SQUARE_KILOMETRES:
        wet_pixels_in_driving_cells = 0
        wet_pixels_next_to_driving_cells = 0
        wet_pixels = 0
        for country, curves in curves_by_country.items():
            wet_pixels_per_cell = flood_map_pixels_by_country[
                country
            ].wet_pixels_per_cell
            drives = (
                np.nan_to_num(curves.upstream_area / SQUARE_METRES_PER_SQUARE_KILOMETRE)
                >= minimum_upstream_area
            )
            is_next_to_driving_cell = ~drives & maximum_filter(
                drives, size=ADJACENT_CELLS_WINDOW
            )
            wet_pixels_in_driving_cells += int(wet_pixels_per_cell[drives].sum())
            wet_pixels_next_to_driving_cells += int(
                wet_pixels_per_cell[is_next_to_driving_cell].sum()
            )
            wet_pixels += int(wet_pixels_per_cell.sum())
        distances.append(
            DrivingCellDistance(
                minimum_upstream_area_square_kilometres=minimum_upstream_area,
                wet_pixels=wet_pixels,
                share_in_driving_cells=round(
                    wet_pixels_in_driving_cells / wet_pixels, SHARE_DECIMALS
                ),
                share_next_to_driving_cells=round(
                    wet_pixels_next_to_driving_cells / wet_pixels, SHARE_DECIMALS
                ),
                share_farther_away=round(
                    (
                        wet_pixels
                        - wet_pixels_in_driving_cells
                        - wet_pixels_next_to_driving_cells
                    )
                    / wet_pixels,
                    SHARE_DECIMALS,
                ),
            )
        )
    for distance in distances:
        print(
            f"Cells drive from {distance.minimum_upstream_area_square_kilometres:g} km2: of the "
            f"{distance.wet_pixels} wet pixels, {distance.share_in_driving_cells:.1%} lie in a "
            f"cell that drives, {distance.share_next_to_driving_cells:.1%} in a cell next to "
            f"one and {distance.share_farther_away:.1%} farther away"
        )
    return distances


def count_flooded_cells(
    curves_by_country: dict[str, GlofasReturnPeriodCurves],
    flood_map_pixels_by_country: dict[str, FloodMapPixels],
) -> list[FloodedCells]:
    """
    Per class of upstream area, the share of the cells that have flooding in the widest flood
    map: per country and for all countries together. It shows from which river size the flood
    maps hold floods.
    """
    class_bounds = list(pairwise(UPSTREAM_AREA_CLASS_BOUNDS))
    flood_map_return_period = next(
        iter(flood_map_pixels_by_country.values())
    ).flood_map_return_period
    counts = {
        (country, bounds): [0, 0]
        for country in [*curves_by_country, ALL_COUNTRIES]
        for bounds in class_bounds
    }
    for country, curves in curves_by_country.items():
        wet_pixels_per_cell = flood_map_pixels_by_country[country].wet_pixels_per_cell
        pixels_per_cell = flood_map_pixels_by_country[country].pixels_per_cell
        is_inside_flood_map = pixels_per_cell == pixels_per_cell.max()
        upstream_area = np.nan_to_num(
            curves.upstream_area / SQUARE_METRES_PER_SQUARE_KILOMETRE
        )
        for bounds in class_bounds:
            is_in_class = (
                is_inside_flood_map
                & (upstream_area >= bounds[0])
                & (upstream_area < bounds[1])
            )
            for key in ((country, bounds), (ALL_COUNTRIES, bounds)):
                counts[key][0] += int(is_in_class.sum())
                counts[key][1] += int((wet_pixels_per_cell[is_in_class] > 0).sum())

    flooded_cells = [
        FloodedCells(
            country=country,
            flood_map_return_period=flood_map_return_period,
            minimum_upstream_area_square_kilometres=bounds[0],
            maximum_upstream_area_square_kilometres=bounds[1],
            cells=cells,
            cells_with_flooding=cells_with_flooding,
            share_with_flooding=round(cells_with_flooding / cells, SHARE_DECIMALS),
        )
        for (country, bounds), (cells, cells_with_flooding) in counts.items()
    ]
    for row in flooded_cells:
        if row.country == ALL_COUNTRIES:
            print(
                f"Cells of {row.minimum_upstream_area_square_kilometres} to "
                f"{row.maximum_upstream_area_square_kilometres} km2: "
                f"{row.cells_with_flooding} of {row.cells} have flooding "
                f"({row.share_with_flooding:.0%})"
            )
    return flooded_cells


def plot_flooded_cells(flooded_cells: list[FloodedCells], path: Path) -> None:
    """The share of cells with flooding per class of upstream area, for all countries together."""
    rows = [row for row in flooded_cells if row.country == ALL_COUNTRIES]
    figure, axis = plt.subplots(figsize=(7.0, 5.2), constrained_layout=True)
    bars = axis.bar(
        [row.minimum_upstream_area_square_kilometres for row in rows],
        [row.share_with_flooding for row in rows],
        width=UPSTREAM_AREA_CLASS_WIDTH,
        align="edge",
        edgecolor="white",
        color=[
            (
                ABOVE_MINIMUM_COLOUR
                if row.minimum_upstream_area_square_kilometres
                >= MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES
                else BELOW_MINIMUM_COLOUR
            )
            for row in rows
        ],
    )
    axis.bar_label(
        bars,
        labels=[f"{row.share_with_flooding:.0%}" for row in rows],
        fontsize="small",
    )
    axis.axvline(
        MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES,
        color=MINIMUM_LINE_COLOUR,
        linestyle="--",
        label=f"{MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES:g} km²: cells drive the footprint from here (draft)",
    )
    axis.axvline(
        GLOFAS_PRODUCTS_MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES,
        color=GLOFAS_PRODUCTS_LINE_COLOUR,
        linestyle=":",
        linewidth=2,
        label=f"{GLOFAS_PRODUCTS_MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES:g} km²: GloFAS shows its own forecasts from here",
    )
    axis.set_title(
        f"GloFAS cells with flooding in the {rows[0].flood_map_return_period}-year flood maps",
        fontsize="large",
    )
    axis.set_xlabel("Upstream area of the GloFAS cell (km²)", fontsize="large")
    axis.set_ylabel("Share of the cells", fontsize="large")
    axis.set_xlim(UPSTREAM_AREA_CLASS_BOUNDS[0], UPSTREAM_AREA_CLASS_BOUNDS[-1])
    axis.set_ylim(0, 1.08)
    axis.yaxis.set_major_formatter(PercentFormatter(xmax=1))
    axis.spines[["top", "right"]].set_visible(False)
    figure.legend(loc="outside lower center", fontsize="small", frameon=False)
    figure.savefig(path, dpi=FIGURE_RESOLUTION_DOTS_PER_INCH)
    plt.close(figure)
    print(f"Wrote {path}")


def load_target_admin_levels() -> dict[str, int]:
    """The admin level of the alert areas per country, from the pipeline's flood config."""
    config_reader = ConfigReader(source_target=None, infra_only=False)
    if not config_reader.load_all(FLOODS_CONFIG_PATH) or config_reader.config is None:
        raise RuntimeError(f"Could not load {FLOODS_CONFIG_PATH}")
    return {
        str(country_config.country_code_iso_3): country_config.target_admin_level
        for country_config in config_reader.config.country_configs.values()
    }


def load_alert_areas(
    seed_repo_path: Path, country: str, admin_level: int
) -> dict[str, BaseGeometry]:
    """The boundary of the area of each station's alert, for the stations that have one."""
    _, alert_configs = load_stations_and_alert_configs(
        seed_repo_path, country, admin_level
    )
    admin_areas = load_admin_areas(seed_repo_path, country, admin_level)
    alert_areas: dict[str, BaseGeometry] = {}
    for alert_config in alert_configs:
        boundary, _ = determine_spatial_extent(
            alert_config.spatial_extent_place_codes, admin_areas
        )
        if boundary is not None:
            alert_areas[alert_config.spatial_extent_name] = boundary
    return alert_areas


def check_gumbel_scale_sensitivity(
    seed_repo_path: Path,
    curves_by_country: dict[str, GlofasReturnPeriodCurves],
    alert_areas_by_country: dict[str, dict[str, BaseGeometry]],
    global_forecast_path: Path,
) -> list[GumbelScaleSensitivity]:
    """
    Per minimum curve scale, the large-river cells it switches off: in each country and in the
    areas of its alerts, where the footprints are. And how many of the cells above the high
    return period in one forecast it switches off: a near-flat curve turns a small discharge
    into a high return period.
    """
    # Per country and area: the curve scale and the peak return period of the large-river cells.
    cells: dict[tuple[str, str], ForecastCells] = {}
    with xr.open_dataset(global_forecast_path) as forecast:
        for country, curves in curves_by_country.items():
            is_large_river = find_country_cells(
                seed_repo_path, country, curves
            ).is_large_river
            # Every cell that an alert area touches: a footprint is driven by the cells around it.
            is_in_alert_area = geometry_mask(
                [mapping(unary_union(list(alert_areas_by_country[country].values())))],
                out_shape=curves.location.shape,
                transform=curves.transform,
                invert=True,
                all_touched=True,
            )
            peak_discharge, peak_return_period = _compute_peaks(forecast, curves)
            for area, is_in_area in (
                (WHOLE_COUNTRY, is_large_river),
                (ALERT_AREAS, is_large_river & is_in_alert_area),
            ):
                cells[(country, area)] = ForecastCells(
                    scale=curves.scale[is_in_area],
                    peak_discharge=peak_discharge[is_in_area],
                    peak_return_period=peak_return_period[is_in_area],
                )
    for area in (WHOLE_COUNTRY, ALERT_AREAS):
        country_cells = [cells[(country, area)] for country in curves_by_country]
        cells[(ALL_COUNTRIES, area)] = ForecastCells(
            scale=np.concatenate([c.scale for c in country_cells]),
            peak_discharge=np.concatenate([c.peak_discharge for c in country_cells]),
            peak_return_period=np.concatenate(
                [c.peak_return_period for c in country_cells]
            ),
        )

    sensitivities: list[GumbelScaleSensitivity] = []
    for (country, area), forecast_cells in cells.items():
        with np.errstate(invalid="ignore"):
            is_at_minimum_return_period = (
                forecast_cells.peak_return_period >= MINIMUM_RETURN_PERIOD_YEARS
            )
            is_above_high_return_period = (
                forecast_cells.peak_return_period >= HIGH_RETURN_PERIOD
            )
        for minimum_scale in MINIMUM_GUMBEL_SCALES_CUBIC_METRES_PER_SECOND:
            does_not_drive = forecast_cells.scale < minimum_scale
            sensitivities.append(
                GumbelScaleSensitivity(
                    country=country,
                    area=area,
                    minimum_scale=minimum_scale,
                    large_river_cells=len(forecast_cells.scale),
                    cells_not_driving=int(does_not_drive.sum()),
                    share_not_driving=round(
                        float(does_not_drive.mean()), SHARE_DECIMALS
                    ),
                    cells_at_minimum_return_period_not_driving=int(
                        (is_at_minimum_return_period & does_not_drive).sum()
                    ),
                    cells_above_high_return_period=int(
                        is_above_high_return_period.sum()
                    ),
                    cells_above_high_return_period_not_driving=int(
                        (is_above_high_return_period & does_not_drive).sum()
                    ),
                    highest_discharge_of_those_cells=round(
                        float(
                            np.max(
                                forecast_cells.peak_discharge,
                                initial=0.0,
                                where=is_above_high_return_period & does_not_drive,
                            )
                        ),
                        DISCHARGE_DECIMALS,
                    ),
                )
            )
    for sensitivity in sensitivities:
        print(
            f"{sensitivity.country}, {sensitivity.area}, cells drive from a curve scale of "
            f"{sensitivity.minimum_scale:g} m3/s: {sensitivity.cells_not_driving} of "
            f"{sensitivity.large_river_cells} large-river cells do not drive "
            f"({sensitivity.share_not_driving:.1%}); of the "
            f"{sensitivity.cells_above_high_return_period} cells above "
            f"{HIGH_RETURN_PERIOD:g} years, "
            f"{sensitivity.cells_above_high_return_period_not_driving} do not drive, with up "
            f"to {sensitivity.highest_discharge_of_those_cells:g} m3/s; "
            f"{sensitivity.cells_at_minimum_return_period_not_driving} of the cells that do "
            f"not drive are at {MINIMUM_RETURN_PERIOD_YEARS:g} years or more"
        )
    return sensitivities


def count_possible_empty_footprints(
    seed_repo_path: Path, alert_areas_by_country: dict[str, dict[str, BaseGeometry]]
) -> list[PossibleEmptyFootprints]:
    """
    Below the lowest flood map, depth is that map's depth scaled down. So at a low alert level a
    footprint is empty when the lowest map is nowhere deep enough in the alert's area to reach
    the minimum flood depth. Counted per return period and minimum flood depth, as if every cell
    in the area is at that return period.
    """
    # Per station: the greatest depth of the lowest flood map inside its alert area.
    greatest_depths: dict[str, float] = {}
    lowest_map_return_period = 0
    for country, alert_areas in alert_areas_by_country.items():
        flood_depth_provider = load_flood_depth_provider(seed_repo_path, country)
        lowest_map_return_period = min(flood_depth_provider.available_return_periods)
        lowest_map = flood_depth_provider.get_raster(lowest_map_return_period)
        for station_code, boundary in alert_areas.items():
            depth = create_raster_geometry_clipper(boundary, lowest_map).clip(
                lowest_map
            )
            greatest_depths[f"{country} {station_code}"] = float(
                np.max(depth.array, initial=0.0, where=depth.array != depth.nodata)
            )
    covered_stations = {
        station: depth for station, depth in greatest_depths.items() if depth > 0
    }

    possible_empty_footprints: list[PossibleEmptyFootprints] = []
    for return_period in LOW_ALERT_RETURN_PERIODS:
        depth_fraction = (return_period - ZERO_DEPTH_RETURN_PERIOD) / (
            lowest_map_return_period - ZERO_DEPTH_RETURN_PERIOD
        )
        for minimum_flood_depth in MINIMUM_FLOOD_DEPTHS_METRES:
            stations_with_empty_footprint = [
                station
                for station, greatest_depth in covered_stations.items()
                if greatest_depth * depth_fraction < minimum_flood_depth
            ]
            possible_empty_footprints.append(
                PossibleEmptyFootprints(
                    return_period=return_period,
                    minimum_flood_depth_metres=minimum_flood_depth,
                    stations=len(covered_stations),
                    stations_outside_flood_maps=len(greatest_depths)
                    - len(covered_stations),
                    stations_with_empty_footprint=len(stations_with_empty_footprint),
                    station_codes_with_empty_footprint=", ".join(
                        stations_with_empty_footprint
                    ),
                )
            )
    print(
        f"The flood maps do not cover the area of "
        f"{possible_empty_footprints[0].stations_outside_flood_maps} of "
        f"{len(greatest_depths)} stations"
    )
    for row in possible_empty_footprints:
        print(
            f"Every cell at {row.return_period:g} years, at least "
            f"{row.minimum_flood_depth_metres:g} m: {row.stations_with_empty_footprint} of "
            f"{row.stations} stations have an empty footprint "
            f"({row.station_codes_with_empty_footprint or 'none'})"
        )
    return possible_empty_footprints


def write_rows(
    rows: (
        list[FloodDepthSensitivity]
        | list[UpstreamAreaSensitivity]
        | list[DrivingCellDistance]
        | list[FloodedCells]
        | list[GumbelScaleSensitivity]
        | list[PossibleEmptyFootprints]
    ),
    path: Path,
) -> None:
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(asdict(rows[0])))
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)
    print(f"Wrote {path}")


def _extract_median_discharge(
    inputs: Inputs, triggered_station: TriggeredStation
) -> RasterData:
    median_discharge = extract_median_discharge(
        inputs.netcdf_paths, triggered_station.peak_lead_time
    )
    if median_discharge is None:
        raise FileNotFoundError("No forecast at the station's peak lead time")
    return median_discharge


def _measure_exposed_population(
    inputs: Inputs,
    triggered_station: TriggeredStation,
    triggered_stations: list[TriggeredStation],
    cell_return_periods: RasterData,
    minimum_flood_depth: float,
) -> float:
    flood_depth = compute_flood_depth(
        time_interval_severities=triggered_station.time_interval_severities,
        cell_return_periods=cell_return_periods,
        boundary=triggered_station.boundary,
        flood_depth_provider=inputs.flood_depth_provider,
        regridding_method=REGRIDDING_METHOD,
        minimum_flood_depth=minimum_flood_depth,
        minimum_return_period=MINIMUM_RETURN_PERIOD_YEARS,
    )
    if flood_depth is None:
        raise RuntimeError(
            f"The flood maps do not cover station {triggered_station.station.id}"
        )
    return measure_footprint(
        Footprint(
            triggered_station.station.id,
            NEW,
            REGRIDDING_METHOD,
            minimum_flood_depth,
            flood_depth,
        ),
        triggered_stations,
        inputs,
    ).exposed_population


def _get_station_cell_return_period(
    cell_return_periods: RasterData, triggered_station: TriggeredStation
) -> float:
    transform = cell_return_periods.transform
    station = triggered_station.station
    row = int((station.lat - transform.f) // transform.e)
    column = int((station.lon - transform.c) // transform.a)
    return round(float(cell_return_periods.array[row, column]), 3)


def _compute_peaks(
    forecast: xr.Dataset, curves: GlofasReturnPeriodCurves
) -> tuple[np.ndarray, np.ndarray]:
    """Per cell of the curves, the highest discharge and the highest return period over the lead times of the flood alerts."""
    row_count, column_count = curves.location.shape
    latitudes = curves.transform.f + (np.arange(row_count) + 0.5) * curves.transform.e
    longitudes = (
        curves.transform.c + (np.arange(column_count) + 0.5) * curves.transform.a
    )
    discharge = (
        forecast[DISCHARGE_VARIABLE]
        .isel(time=slice(0, len(FLOOD_LEAD_TIME_SPECTRUM)))
        .sel(
            {LATITUDE: latitudes, LONGITUDE: longitudes},
            method="nearest",
            tolerance=COORDINATE_TOLERANCE_DEGREES,
        )
        .to_numpy()
        .astype(np.float64)
    )
    discharge[discharge < 0] = np.nan
    return_periods = compute_return_period(
        discharge,
        curves.location[np.newaxis],
        curves.scale[np.newaxis],
        maximum_return_period=np.inf,
    )
    return _get_highest(discharge), _get_highest(return_periods)


def _get_highest(values: np.ndarray) -> np.ndarray:
    """The highest value over the first axis. Infinite counts as the highest; all-missing gives NaN."""
    is_missing = np.isnan(values).all(axis=0)
    highest = np.max(np.nan_to_num(values, nan=-np.inf, posinf=np.inf), axis=0)
    return np.where(is_missing, np.nan, highest)


if __name__ == "__main__":
    main()
