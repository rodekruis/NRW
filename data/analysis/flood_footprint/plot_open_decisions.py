"""
Charts that explain two open decisions on the flood footprint (AB#42674): cells with a near-flat
return period curve, and stations on a cell that does not drive the footprint.

Usage (from the data directory):
    uv run python -m analysis.flood_footprint.plot_open_decisions
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from analysis.flood_footprint.check_curve_source import (
    DEFAULT_RETURN_PERIOD_CURVES_DIRECTORY,
    find_cells_containing,
    fit_gumbel_curve,
    SQUARE_METRES_PER_SQUARE_KILOMETRE,
)
from analysis.flood_footprint.seed_repo_inputs import (
    load_admin_areas,
    STATION_THRESHOLDS_DIRECTORY,
)
from matplotlib.axes import Axes
from matplotlib.colors import LogNorm
from matplotlib.patches import Rectangle
from pipelines.flood.constants import (
    GLOFAS_VERSION,
    MINIMUM_GUMBEL_SCALE_CUBIC_METRES_PER_SECOND,
    MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES,
)
from pipelines.infra.data_types.glofas_return_period_curves import (
    get_glofas_return_period_curves_filename,
    GlofasReturnPeriodCurves,
)
from rasterio.features import geometry_mask
from shapely.geometry import mapping
from shapely.ops import unary_union
from shared.data_helpers import get_seed_data_repo_path, target_countries_iso_a3

DEFAULT_RESULTS_DIRECTORY = Path(__file__).parent / "results"

# A river with an ordinary curve, to set a near-flat curve against.
ORDINARY_CURVE_COUNTRY = "MWI"
ORDINARY_CURVE_STATION_CODE = "G1724"
# The near-flat example is the cell with the median scale among the near-flat cells of this country.
NEAR_FLAT_CURVE_COUNTRY = "ETH"

CURVE_RETURN_PERIODS = np.geomspace(1.5, 500, 200)
MARKED_RETURN_PERIODS = (2, 5, 10, 20, 50, 100, 200, 500)
LOWEST_MARKED_RETURN_PERIOD, HIGHEST_MARKED_RETURN_PERIOD = 2, 500
# Cells shown around a station, on each side of its own cell.
NEIGHBOURHOOD_CELLS = 3
KILOMETRES_PER_DEGREE = 111.32

FIGURE_RESOLUTION_DOTS_PER_INCH = 150
CURVE_COLOUR = "#1b6ca8"
STATION_CELL_COLOUR = "red"
DRIVING_CELL_COLOUR = "black"
UPSTREAM_AREA_COLOUR_MAP = "Blues"


@dataclass
class Cell:
    row: int
    column: int
    latitude: float
    longitude: float
    location: float
    scale: float
    upstream_area_square_kilometres: float


@dataclass
class NearFlatCellCount:
    country: str
    large_river_cells: int
    near_flat_cells: int
    near_flat_share: float


@dataclass
class StationOnSmallStream:
    country: str
    station_code: str
    station_name: str
    own_cell: Cell
    nearest_driving_cell: Cell
    distance_kilometres: float
    curves: GlofasReturnPeriodCurves


def main() -> None:
    arguments = parse_arguments()
    seed_repo_path = get_seed_data_repo_path()
    results_directory: Path = arguments.results_directory
    results_directory.mkdir(parents=True, exist_ok=True)

    curves_by_country = {
        country: GlofasReturnPeriodCurves.from_geotiff(
            (
                arguments.return_period_curves_directory
                / get_glofas_return_period_curves_filename(country, GLOFAS_VERSION)
            ).read_bytes()
        )
        for country in arguments.countries
    }
    stations_by_country = {
        country: json.loads(
            (
                seed_repo_path
                / STATION_THRESHOLDS_DIRECTORY
                / f"{country}_station_thresholds.json"
            ).read_text(encoding="utf-8")
        )
        for country in arguments.countries
    }

    near_flat_masks = {
        country: find_near_flat_cells(seed_repo_path, country, curves)
        for country, curves in curves_by_country.items()
    }
    write_near_flat_cell_counts(
        [
            count_near_flat_cells(country, *near_flat_masks[country])
            for country in arguments.countries
        ],
        results_directory / "near_flat_curve_cells.csv",
    )
    plot_near_flat_curve(
        ordinary_cell=get_station_cell(
            curves_by_country[ORDINARY_CURVE_COUNTRY],
            next(
                station
                for station in stations_by_country[ORDINARY_CURVE_COUNTRY]
                if station["station_code"] == ORDINARY_CURVE_STATION_CODE
            ),
        ),
        near_flat_cell=get_median_scale_cell(
            curves_by_country[NEAR_FLAT_CURVE_COUNTRY],
            near_flat_masks[NEAR_FLAT_CURVE_COUNTRY][1],
        ),
        path=results_directory / "near_flat_curve.png",
    )
    plot_stations_on_small_streams(
        [
            station_on_small_stream
            for country in arguments.countries
            for station_on_small_stream in find_stations_on_small_streams(
                country, stations_by_country[country], curves_by_country[country]
            )
        ],
        results_directory / "stations_on_small_streams.png",
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--countries", nargs="+", default=sorted(target_countries_iso_a3)
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


def find_near_flat_cells(
    seed_repo_path: Path, country: str, curves: GlofasReturnPeriodCurves
) -> tuple[np.ndarray, np.ndarray]:
    """Masks of the large-river cells inside the country, and of those with a near-flat curve."""
    admin_areas = load_admin_areas(seed_repo_path, country, admin_level=0)
    country_geometry = unary_union(
        [admin_area.to_geometry() for admin_area in admin_areas.admin_areas.values()]
    )
    is_inside_country = geometry_mask(
        [mapping(country_geometry)],
        out_shape=curves.location.shape,
        transform=curves.transform,
        invert=True,
    )
    with np.errstate(invalid="ignore"):
        is_large_river = (
            is_inside_country
            & np.isfinite(curves.scale)
            & (
                curves.upstream_area
                >= MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES
                * SQUARE_METRES_PER_SQUARE_KILOMETRE
            )
        )
        is_near_flat = is_large_river & (
            curves.scale < MINIMUM_GUMBEL_SCALE_CUBIC_METRES_PER_SECOND
        )
    return is_large_river, is_near_flat


def count_near_flat_cells(
    country: str, is_large_river: np.ndarray, is_near_flat: np.ndarray
) -> NearFlatCellCount:
    large_river_cells = int(is_large_river.sum())
    near_flat_cells = int(is_near_flat.sum())
    return NearFlatCellCount(
        country=country,
        large_river_cells=large_river_cells,
        near_flat_cells=near_flat_cells,
        near_flat_share=round(near_flat_cells / large_river_cells, 3),
    )


def write_near_flat_cell_counts(counts: list[NearFlatCellCount], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(asdict(counts[0])))
        writer.writeheader()
        writer.writerows(asdict(count) for count in counts)
    for count in counts:
        print(
            f"{count.country}: {count.near_flat_cells} of {count.large_river_cells} "
            f"large-river cells have a near-flat curve ({count.near_flat_share:.0%})"
        )
    print(f"Wrote {path}")


def get_median_scale_cell(
    curves: GlofasReturnPeriodCurves, is_near_flat: np.ndarray
) -> Cell:
    rows, columns = np.nonzero(is_near_flat)
    median_index = np.argsort(curves.scale[rows, columns])[len(rows) // 2]
    return get_cell(curves, int(rows[median_index]), int(columns[median_index]))


def get_station_cell(curves: GlofasReturnPeriodCurves, station: dict) -> Cell:
    """
    The cell of a station. A station on a cell edge lies in several cells: take the one whose
    curve its thresholds lie on.
    """
    implied_location, _, _ = fit_gumbel_curve(
        return_periods=[
            threshold["return_period"] for threshold in station["thresholds"]
        ],
        discharges=[
            threshold["threshold_value"] for threshold in station["thresholds"]
        ],
    )
    cells = [
        get_cell(curves, row, column)
        for row, column in find_cells_containing(
            curves, latitude=station["lat"], longitude=station["lon"]
        )
    ]
    return min(cells, key=lambda cell: abs(cell.location - implied_location))


def get_cell(curves: GlofasReturnPeriodCurves, row: int, column: int) -> Cell:
    return Cell(
        row=row,
        column=column,
        latitude=curves.transform.f + (row + 0.5) * curves.transform.e,
        longitude=curves.transform.c + (column + 0.5) * curves.transform.a,
        location=float(curves.location[row, column]),
        scale=float(curves.scale[row, column]),
        upstream_area_square_kilometres=float(
            curves.upstream_area[row, column] / SQUARE_METRES_PER_SQUARE_KILOMETRE
        ),
    )


def plot_near_flat_curve(ordinary_cell: Cell, near_flat_cell: Cell, path: Path) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(11, 4.2), constrained_layout=True)
    for axis, cell, title in (
        (
            axes[0],
            ordinary_cell,
            f"An ordinary curve, at {ORDINARY_CURVE_COUNTRY} {ORDINARY_CURVE_STATION_CODE}",
        ),
        (
            axes[1],
            near_flat_cell,
            (
                f"A near-flat curve, in {NEAR_FLAT_CURVE_COUNTRY} at "
                f"{near_flat_cell.latitude:.3f}, {near_flat_cell.longitude:.3f}"
            ),
        ),
    ):
        axis.plot(
            CURVE_RETURN_PERIODS,
            get_gumbel_discharge(cell, CURVE_RETURN_PERIODS),
            color=CURVE_COLOUR,
            linewidth=2,
        )
        discharge_range = float(
            get_gumbel_discharge(cell, np.array([HIGHEST_MARKED_RETURN_PERIOD]))[0]
            - get_gumbel_discharge(cell, np.array([LOWEST_MARKED_RETURN_PERIOD]))[0]
        )
        axis.set_title(
            f"{title} (upstream area {cell.upstream_area_square_kilometres:,.0f} km²)\n"
            f"from a {LOWEST_MARKED_RETURN_PERIOD}-year to a {HIGHEST_MARKED_RETURN_PERIOD}-year "
            f"flood takes {_format_discharge(discharge_range)} m³/s more",
            fontsize="medium",
        )
        axis.set_xscale("log")
        axis.set_xticks(MARKED_RETURN_PERIODS, [str(r) for r in MARKED_RETURN_PERIODS])
        axis.minorticks_off()
        axis.set_xlabel("Return period (years)")
        axis.set_ylabel("Discharge (m³/s)")
        axis.set_ylim(bottom=0)
        axis.grid(alpha=0.3)
    figure.savefig(path, dpi=FIGURE_RESOLUTION_DOTS_PER_INCH, bbox_inches="tight")
    plt.close(figure)
    print(f"Wrote {path}")


def get_gumbel_discharge(cell: Cell, return_periods: np.ndarray) -> np.ndarray:
    return cell.location - cell.scale * np.log(-np.log(1 - 1 / return_periods))


def _format_discharge(discharge: float) -> str:
    return f"{discharge:,.0f}" if discharge >= 100 else f"{discharge:.2g}"


def find_stations_on_small_streams(
    country: str, stations: list[dict], curves: GlofasReturnPeriodCurves
) -> list[StationOnSmallStream]:
    """Stations whose own cell does not drive the footprint, with the nearest cell that does."""
    with np.errstate(invalid="ignore"):
        drives_footprint = (
            curves.upstream_area
            >= MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES
            * SQUARE_METRES_PER_SQUARE_KILOMETRE
        ) & (curves.scale >= MINIMUM_GUMBEL_SCALE_CUBIC_METRES_PER_SECOND)
    driving_rows, driving_columns = np.nonzero(drives_footprint)

    stations_on_small_streams: list[StationOnSmallStream] = []
    for station in stations:
        own_cell = get_station_cell(curves, station)
        if drives_footprint[own_cell.row, own_cell.column]:
            continue
        # Like the pipeline: the nearest cell centre in degrees.
        nearest = int(
            np.argmin(
                np.hypot(
                    (driving_rows + 0.5) * curves.transform.e
                    + curves.transform.f
                    - station["lat"],
                    (driving_columns + 0.5) * curves.transform.a
                    + curves.transform.c
                    - station["lon"],
                )
            )
        )
        nearest_driving_cell = get_cell(
            curves, int(driving_rows[nearest]), int(driving_columns[nearest])
        )
        stations_on_small_streams.append(
            StationOnSmallStream(
                country=country,
                station_code=station["station_code"],
                station_name=station["station_name"],
                own_cell=own_cell,
                nearest_driving_cell=nearest_driving_cell,
                distance_kilometres=KILOMETRES_PER_DEGREE
                * math.hypot(
                    nearest_driving_cell.latitude - own_cell.latitude,
                    (nearest_driving_cell.longitude - own_cell.longitude)
                    * math.cos(math.radians(own_cell.latitude)),
                ),
                curves=curves,
            )
        )
    return stations_on_small_streams


def plot_stations_on_small_streams(
    stations: list[StationOnSmallStream], path: Path
) -> None:
    figure, axes = plt.subplots(
        1,
        len(stations),
        figsize=(4.3 * len(stations), 4.9),
        squeeze=False,
        constrained_layout=True,
    )
    for axis, station in zip(axes[0], stations, strict=True):
        _plot_station_neighbourhood(axis, station)
        print(
            f"{station.country} {station.station_code}: own cell "
            f"{station.own_cell.upstream_area_square_kilometres:,.0f} km2, nearest driving cell "
            f"{station.distance_kilometres:.0f} km away with "
            f"{station.nearest_driving_cell.upstream_area_square_kilometres:,.0f} km2"
        )
    figure.savefig(path, dpi=FIGURE_RESOLUTION_DOTS_PER_INCH, bbox_inches="tight")
    plt.close(figure)
    print(f"Wrote {path}")


def _plot_station_neighbourhood(axis: Axes, station: StationOnSmallStream) -> None:
    """Upstream area (km²) of the cells around a station; its own cell and the nearest driving cell are outlined."""
    own_cell = station.own_cell
    size = 2 * NEIGHBOURHOOD_CELLS + 1
    first_row = own_cell.row - NEIGHBOURHOOD_CELLS
    first_column = own_cell.column - NEIGHBOURHOOD_CELLS
    upstream_area = (
        station.curves.upstream_area[
            first_row : first_row + size, first_column : first_column + size
        ]
        / SQUARE_METRES_PER_SQUARE_KILOMETRE
    )
    axis.imshow(
        upstream_area,
        cmap=UPSTREAM_AREA_COLOUR_MAP,
        norm=LogNorm(vmin=10, vmax=100_000),
    )
    for row in range(size):
        for column in range(size):
            value = upstream_area[row, column]
            is_large_river = value >= MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES
            axis.text(
                column,
                row,
                f"{value:,.0f}" if np.isfinite(value) else "sea",
                ha="center",
                va="center",
                fontsize=6.5,
                fontweight="bold" if is_large_river else "normal",
                color="white" if value >= 5_000 else "black",
            )
    for cell, colour in (
        (station.nearest_driving_cell, DRIVING_CELL_COLOUR),
        (own_cell, STATION_CELL_COLOUR),
    ):
        row, column = cell.row - first_row, cell.column - first_column
        if 0 <= row < size and 0 <= column < size:
            axis.add_patch(
                Rectangle(
                    (column - 0.5, row - 0.5),
                    1,
                    1,
                    fill=False,
                    edgecolor=colour,
                    linewidth=2.5,
                )
            )
    name = f" ({station.station_name})" if station.station_name.lower() != "na" else ""
    axis.set_title(
        f"{station.country} {station.station_code}{name}\n"
        f"own cell (red): {own_cell.upstream_area_square_kilometres:,.0f} km²\n"
        f"nearest driving cell (black): {station.distance_kilometres:.0f} km away, "
        f"{station.nearest_driving_cell.upstream_area_square_kilometres:,.0f} km²",
        fontsize="small",
    )
    axis.set_xticks([])
    axis.set_yticks([])


if __name__ == "__main__":
    main()
