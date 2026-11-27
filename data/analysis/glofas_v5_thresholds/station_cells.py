"""Place each station on one GloFAS cell, the same in v4 and v5, so the result does not depend on how a coordinate on a cell boundary is rounded."""

from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from enum import StrEnum
from functools import cache
from pathlib import Path

import numpy as np
import xarray as xr
from analysis.glofas_v5_thresholds.gumbel import gumbel_threshold
from analysis.glofas_v5_thresholds.stations import GLOFAS_CELL_SIZE_DEGREES, Station
from data_management.seed_data_management.flood.build_glofas_return_period_curves import (
    LATITUDE,
    LOCATION,
    LONGITUDE,
    SCALE,
    UPSTREAM_AREA,
)

# The smallest upstream area of a GloFAS v4 reporting point, see https://confluence.ecmwf.int/spaces/CEMS/pages/554157279/Pre-operational+GloFAS+release+v5
MINIMUM_V4_UPSTREAM_AREA_SQUARE_KILOMETRES = 250
SQUARE_METRES_PER_SQUARE_KILOMETRE = 1e6
# The seed thresholds were computed from ECMWF's v4 curves; small differences come from rounding in older files.
SEED_THRESHOLD_TOLERANCE = 0.02
SEED_CHECK_RETURN_PERIODS = [1.5, 2.0, 5.0, 10.0, 20.0]
# GloFAS places a station on a river cell right around it; without its own cell for the station, the largest one.
RIVER_SEARCH_RADIUS_CELLS = 1
# A coordinate within this many degrees of a cell edge lies on the edge.
EDGE_TOLERANCE_DEGREES = 1e-6
# Checked by hand in the GloFAS viewer, for the stations off the river.
GLOFAS_VIEWER_RIVER_CELLS_PATH = Path(__file__).parent / "glofas_viewer_river_cells.csv"


class Placement(StrEnum):
    INSIDE_CELL = "inside_cell"
    ON_CELL_BOUNDARY = "on_cell_boundary"
    MOVED_TO_RIVER = "moved_to_river"


@dataclass(frozen=True)
class StationCell:
    latitude: float
    longitude: float
    placement: Placement
    touching_cells: int
    upstream_area_square_kilometres: float
    seed_thresholds_on_cell: bool
    # Of the cells the station's coordinates touch; below the reporting-point minimum, the forecast may come from a dry cell.
    smallest_touching_upstream_area_square_kilometres: float


def locate_station_cell(station: Station, v4_curves: xr.Dataset) -> StationCell:
    """The cell for a station's forecast and thresholds.

    - Inside one cell: that cell.
    - On a cell boundary: of the cells it touches, the one with today's thresholds, else the largest river.
    - On a cell draining less than the smallest v4 reporting point: GloFAS's own river cell for the station
      where it was looked up in the GloFAS viewer, else the largest river right around it.
    """
    touching = [
        (latitude, longitude)
        for latitude in _touching_cell_centres(station.latitude)
        for longitude in _touching_cell_centres(station.longitude)
    ]
    described = [
        _describe_cell(v4_curves, station, latitude, longitude)
        for latitude, longitude in touching
    ]
    chosen = max(
        described,
        key=lambda cell: (
            cell.seed_thresholds_on_cell,
            cell.upstream_area_square_kilometres,
        ),
    )
    smallest_touching = min(cell.upstream_area_square_kilometres for cell in described)
    if (
        chosen.upstream_area_square_kilometres
        < MINIMUM_V4_UPSTREAM_AREA_SQUARE_KILOMETRES
    ):
        viewer_cell = _load_glofas_viewer_river_cells().get(station.code)
        if viewer_cell is not None:
            confirmed = _describe_cell(v4_curves, station, *viewer_cell)
            return replace(
                confirmed,
                placement=Placement.MOVED_TO_RIVER,
                touching_cells=len(touching),
                smallest_touching_upstream_area_square_kilometres=smallest_touching,
            )
        return _largest_river_around(
            v4_curves, station, chosen, len(touching), smallest_touching
        )
    return StationCell(
        latitude=chosen.latitude,
        longitude=chosen.longitude,
        placement=(
            Placement.ON_CELL_BOUNDARY if len(touching) > 1 else Placement.INSIDE_CELL
        ),
        touching_cells=len(touching),
        upstream_area_square_kilometres=chosen.upstream_area_square_kilometres,
        seed_thresholds_on_cell=chosen.seed_thresholds_on_cell,
        smallest_touching_upstream_area_square_kilometres=smallest_touching,
    )


@cache
def _load_glofas_viewer_river_cells() -> dict[str, tuple[float, float]]:
    """GloFAS's river cell per station ("LISFLOOD X/Y" in the viewer's reporting point pop-up)."""
    with GLOFAS_VIEWER_RIVER_CELLS_PATH.open(encoding="utf-8") as file:
        return {
            row["station_code"]: (
                float(row["lisflood_latitude"]),
                float(row["lisflood_longitude"]),
            )
            for row in csv.DictReader(file)
        }


def _touching_cell_centres(coordinate: float) -> list[float]:
    cells = coordinate / GLOFAS_CELL_SIZE_DEGREES
    nearest_edge = round(cells)
    if abs(cells - nearest_edge) * GLOFAS_CELL_SIZE_DEGREES < EDGE_TOLERANCE_DEGREES:
        return [
            round((nearest_edge - 0.5) * GLOFAS_CELL_SIZE_DEGREES, 3),
            round((nearest_edge + 0.5) * GLOFAS_CELL_SIZE_DEGREES, 3),
        ]
    return [round((np.floor(cells) + 0.5) * GLOFAS_CELL_SIZE_DEGREES, 3)]


def _describe_cell(
    v4_curves: xr.Dataset, station: Station, latitude: float, longitude: float
) -> StationCell:
    cell = v4_curves.sel({LATITUDE: latitude, LONGITUDE: longitude}, method="nearest")
    location = float(cell[LOCATION])
    scale = float(cell[SCALE])
    return StationCell(
        latitude=latitude,
        longitude=longitude,
        placement=Placement.INSIDE_CELL,
        touching_cells=1,
        upstream_area_square_kilometres=float(cell[UPSTREAM_AREA])
        / SQUARE_METRES_PER_SQUARE_KILOMETRE,
        seed_thresholds_on_cell=bool(
            np.isfinite(location)
            and all(
                np.isclose(
                    station.thresholds[return_period],
                    gumbel_threshold(return_period, location, scale),
                    rtol=SEED_THRESHOLD_TOLERANCE,
                )
                for return_period in SEED_CHECK_RETURN_PERIODS
            )
        ),
        smallest_touching_upstream_area_square_kilometres=np.nan,
    )


def _largest_river_around(
    v4_curves: xr.Dataset,
    station: Station,
    centre: StationCell,
    touching_cells: int,
    smallest_touching: float,
) -> StationCell:
    offsets = range(-RIVER_SEARCH_RADIUS_CELLS, RIVER_SEARCH_RADIUS_CELLS + 1)
    around = [
        _describe_cell(
            v4_curves,
            station,
            round(centre.latitude + row * GLOFAS_CELL_SIZE_DEGREES, 3),
            round(centre.longitude + column * GLOFAS_CELL_SIZE_DEGREES, 3),
        )
        for row in offsets
        for column in offsets
    ]
    largest = max(around, key=lambda cell: cell.upstream_area_square_kilometres)
    return StationCell(
        latitude=largest.latitude,
        longitude=largest.longitude,
        placement=Placement.MOVED_TO_RIVER,
        touching_cells=touching_cells,
        upstream_area_square_kilometres=largest.upstream_area_square_kilometres,
        seed_thresholds_on_cell=largest.seed_thresholds_on_cell,
        smallest_touching_upstream_area_square_kilometres=smallest_touching,
    )
