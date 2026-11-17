"""Data locations, period and extent shared by the drought hindcast analysis scripts."""

import json
import math
from dataclasses import dataclass
from pathlib import Path

from shapely import union_all
from shapely.geometry import shape

DATA_DIRECTORY = Path(__file__).parents[2] / "data" / "drought_hindcast"
REGIONS_FILE = DATA_DIRECTORY / "regions" / "regions.geojson"
CHIRPS_DIRECTORY = DATA_DIRECTORY / "chirps"
SEAS5_DIRECTORY = DATA_DIRECTORY / "seas5"
INTERMEDIATE_DIRECTORY = DATA_DIRECTORY / "intermediate"
OBSERVED_RAINFALL_FILE = INTERMEDIATE_DIRECTORY / "observed_region_rainfall.nc"
FORECAST_RAINFALL_FILE = INTERMEDIATE_DIRECTORY / "forecast_cell_rainfall.nc"
INPUTS_DIRECTORY = Path(__file__).parent / "inputs"
EARLIER_MATRIX_CELLS_FILE = INPUTS_DIRECTORY / "earlier_matrix_cells.csv"
SKILL_REVIEW_GRADES_FILE = INPUTS_DIRECTORY / "skill_review_seas5_grades.csv"
RESULTS_DIRECTORY = Path(__file__).parent / "results"
OBSERVED_SEASONS_FILE = RESULTS_DIRECTORY / "observed_seasons.csv"
FORECAST_ALERTS_FILE = RESULTS_DIRECTORY / "forecast_alerts.csv"
SKILL_FILE = RESULTS_DIRECTORY / "skill_by_lead_time.csv"
EARLIER_MATRIX_CASES_FILE = RESULTS_DIRECTORY / "earlier_matrix_cases.csv"
RELIABLE_LEAD_TIMES_FILE = RESULTS_DIRECTORY / "reliable_lead_times.csv"
SKILL_REVIEW_COMPARISON_FILE = RESULTS_DIRECTORY / "skill_review_comparison.csv"
CHARTS_DIRECTORY = RESULTS_DIRECTORY / "charts"

# First year of both the CHIRPS record and the SEAS5 hindcasts.
FIRST_YEAR = 1981

# Keeps the coarse SEAS5 grid cells that only partly overlap a region.
BOUNDS_MARGIN_DEGREES = 1


@dataclass(frozen=True)
class Bounds:
    west: int
    south: int
    east: int
    north: int


def load_study_bounds() -> Bounds:
    """Whole-degree box around all regions, used as download extent for every source."""
    west, south, east, north = union_all(
        [shape(geometry) for geometry in load_region_geometries().values()]
    ).bounds
    return Bounds(
        west=math.floor(west) - BOUNDS_MARGIN_DEGREES,
        south=math.floor(south) - BOUNDS_MARGIN_DEGREES,
        east=math.ceil(east) + BOUNDS_MARGIN_DEGREES,
        north=math.ceil(north) + BOUNDS_MARGIN_DEGREES,
    )


def load_region_geometries() -> dict[str, dict]:
    """GeoJSON geometry per region key."""
    if not REGIONS_FILE.exists():
        raise FileNotFoundError(
            f"{REGIONS_FILE} not found. Run build_region_shapes first."
        )
    with REGIONS_FILE.open(encoding="utf-8") as file:
        features = json.load(file)["features"]
    return {
        format_region_key(
            feature["properties"]["country_code_iso3"],
            feature["properties"]["region_name"],
        ): feature["geometry"]
        for feature in features
    }


def format_region_key(country_code_iso3: str, region_name: str) -> str:
    return f"{country_code_iso3} {region_name}"
