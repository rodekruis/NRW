"""
Check where the station thresholds come from: at each station, compare the Gumbel curve that its
thresholds imply with the GloFAS return period curve of its cell.

Usage (from the data directory):
    uv run python -m analysis.flood_footprint.check_curve_source
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
from analysis.flood_footprint.seed_repo_inputs import STATION_THRESHOLDS_DIRECTORY
from pipelines.flood.constants import (
    GLOFAS_VERSION,
    MINIMUM_GUMBEL_SCALE_CUBIC_METRES_PER_SECOND,
    MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES,
)
from pipelines.infra.data_types.glofas_return_period_curves import (
    get_glofas_return_period_curves_filename,
    GlofasReturnPeriodCurves,
)
from shared.data_helpers import get_seed_data_repo_path, target_countries_iso_a3

DATA_DIRECTORY = Path(__file__).parents[2] / "data"
DEFAULT_RETURN_PERIOD_CURVES_DIRECTORY = DATA_DIRECTORY / "glofas-return-period-curves"
DEFAULT_OUTPUT_PATH = Path(__file__).parent / "results" / "curve_source_check.csv"

# Two curves are the same when both parameters agree to this relative difference.
SAME_CURVE_RELATIVE_TOLERANCE = 1e-6
# A station this close to a cell edge, in cells, lies in both cells.
CELL_EDGE_TOLERANCE_CELLS = 1e-6
SQUARE_METRES_PER_SQUARE_KILOMETRE = 1_000_000.0


@dataclass
class StationCurveCheck:
    country: str
    station_code: str
    latitude: float
    longitude: float
    implied_location: float
    implied_scale: float
    # Largest difference between a threshold and the fitted Gumbel curve, relative to the threshold.
    largest_threshold_residual: float
    cell_location: float
    cell_scale: float
    cell_upstream_area_square_kilometres: float
    is_same_curve: bool
    # A station on a cell edge lies in two cells, on a corner in four.
    cells_containing_station: int
    cells_containing_station_with_same_curve: int
    # Row and column offset of a neighbouring cell with the implied curve, when the station's own cell differs.
    neighbour_with_same_curve: str


def main() -> None:
    arguments = parse_arguments()
    seed_repo_path = get_seed_data_repo_path()

    checks: list[StationCurveCheck] = []
    for country in arguments.countries:
        curves = GlofasReturnPeriodCurves.from_geotiff(
            (
                arguments.return_period_curves_directory
                / get_glofas_return_period_curves_filename(country, GLOFAS_VERSION)
            ).read_bytes()
        )
        stations = json.loads(
            (
                seed_repo_path
                / STATION_THRESHOLDS_DIRECTORY
                / f"{country}_station_thresholds.json"
            ).read_text(encoding="utf-8")
        )
        checks.extend(check_station(country, station, curves) for station in stations)

    write_checks(checks, arguments.output_path)
    print_summary(checks)


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
    parser.add_argument("--output-path", type=Path, default=DEFAULT_OUTPUT_PATH)
    return parser.parse_args()


def check_station(
    country: str, station: dict, curves: GlofasReturnPeriodCurves
) -> StationCurveCheck:
    implied_location, implied_scale, largest_residual = fit_gumbel_curve(
        return_periods=[
            threshold["return_period"] for threshold in station["thresholds"]
        ],
        discharges=[
            threshold["threshold_value"] for threshold in station["thresholds"]
        ],
    )
    own_cells = find_cells_containing(
        curves, latitude=station["lat"], longitude=station["lon"]
    )

    def is_same_curve(row: int, column: int) -> bool:
        row_count, column_count = curves.location.shape
        if not (0 <= row < row_count and 0 <= column < column_count):
            return False
        return bool(
            np.isclose(
                curves.location[row, column],
                implied_location,
                rtol=SAME_CURVE_RELATIVE_TOLERANCE,
            )
            and np.isclose(
                curves.scale[row, column],
                implied_scale,
                rtol=SAME_CURVE_RELATIVE_TOLERANCE,
            )
        )

    # Report the own cell with the implied curve when there is one, otherwise the first own cell.
    row, column = next(
        (cell for cell in own_cells if is_same_curve(*cell)), own_cells[0]
    )
    neighbours_with_same_curve = [
        f"{row_offset:+d} rows, {column_offset:+d} columns"
        for row_offset in (-1, 0, 1)
        for column_offset in (-1, 0, 1)
        if (row_offset, column_offset) != (0, 0)
        and is_same_curve(row + row_offset, column + column_offset)
    ]

    return StationCurveCheck(
        country=country,
        station_code=station["station_code"],
        latitude=station["lat"],
        longitude=station["lon"],
        implied_location=implied_location,
        implied_scale=implied_scale,
        largest_threshold_residual=largest_residual,
        cell_location=float(curves.location[row, column]),
        cell_scale=float(curves.scale[row, column]),
        cell_upstream_area_square_kilometres=float(
            curves.upstream_area[row, column] / SQUARE_METRES_PER_SQUARE_KILOMETRE
        ),
        is_same_curve=is_same_curve(row, column),
        cells_containing_station=len(own_cells),
        cells_containing_station_with_same_curve=sum(
            is_same_curve(*cell) for cell in own_cells
        ),
        neighbour_with_same_curve="; ".join(neighbours_with_same_curve),
    )


def fit_gumbel_curve(
    return_periods: list[float], discharges: list[float]
) -> tuple[float, float, float]:
    """
    Location and scale of the Gumbel curve through the thresholds, by least squares:
    discharge = location - scale * ln(-ln(1 - 1 / return period)).
    """
    reduced_variate = -np.log(-np.log(1 - 1 / np.asarray(return_periods, dtype=float)))
    design = np.column_stack([np.ones_like(reduced_variate), reduced_variate])
    thresholds = np.asarray(discharges, dtype=float)
    (location, scale), *_ = np.linalg.lstsq(design, thresholds, rcond=None)
    residuals = np.abs(design @ np.array([location, scale]) - thresholds) / thresholds
    return float(location), float(scale), float(residuals.max())


def find_cells_containing(
    curves: GlofasReturnPeriodCurves, latitude: float, longitude: float
) -> list[tuple[int, int]]:
    """The cell of a point; two or four cells when the point lies on a cell edge or corner."""
    row_position = (latitude - curves.transform.f) / curves.transform.e
    column_position = (longitude - curves.transform.c) / curves.transform.a
    return [
        (row, column)
        for row in _indices_containing(row_position)
        for column in _indices_containing(column_position)
    ]


def _indices_containing(position: float) -> list[int]:
    nearest_edge = round(position)
    if abs(position - nearest_edge) <= CELL_EDGE_TOLERANCE_CELLS:
        return [nearest_edge - 1, nearest_edge]
    return [math.floor(position)]


def write_checks(checks: list[StationCurveCheck], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=list(asdict(checks[0])))
        writer.writeheader()
        writer.writerows(asdict(check) for check in checks)
    print(f"Wrote {output_path}")


def print_summary(checks: list[StationCurveCheck]) -> None:
    same_curve = [check for check in checks if check.is_same_curve]
    on_cell_edge = [check for check in checks if check.cells_containing_station > 1]
    print(
        f"{len(same_curve)} of {len(checks)} stations have thresholds on the GloFAS "
        f"{GLOFAS_VERSION} curve of their own cell"
    )
    print(
        "Largest difference between a threshold and its fitted Gumbel curve: "
        f"{max(check.largest_threshold_residual for check in checks):.1e} (relative)"
    )
    print(
        f"{len(on_cell_edge)} stations lie on the edge between cells, where only one cell has the curve "
        "of the thresholds: "
        + ", ".join(
            f"{check.country} {check.station_code}"
            for check in on_cell_edge
            if check.cells_containing_station_with_same_curve == 1
        )
    )
    for check in checks:
        if not check.is_same_curve:
            print(
                f"  {check.country} {check.station_code}: cell location is "
                f"{check.cell_location / check.implied_location:.4f} and cell scale "
                f"{check.cell_scale / check.implied_scale:.4f} times the implied one, "
                f"same curve in neighbour: {check.neighbour_with_same_curve or 'none'}"
            )

    not_driving = [
        check
        for check in checks
        if check.cell_upstream_area_square_kilometres
        < MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES
        or check.cell_scale < MINIMUM_GUMBEL_SCALE_CUBIC_METRES_PER_SECOND
    ]
    print(
        f"{len(not_driving)} stations lie on a cell that does not drive the flood footprint: "
        + ", ".join(f"{check.country} {check.station_code}" for check in not_driving)
    )


if __name__ == "__main__":
    main()
