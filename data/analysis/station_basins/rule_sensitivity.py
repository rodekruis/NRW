"""Vary the station-to-basin rule one choice at a time and measure every variant.

Analysis for spike AB#42674. Starts from the rule of draft PR #99 (see
initial_rule.py) and measures each variant on the same numbers: unit size,
dependence on other stations, and agreement with today's admin-area footprints
and the 10-year flood map.

    uv run python -m analysis.station_basins.rule_sensitivity
"""

import argparse
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

import geopandas as gpd
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio.features
import shapely
from adjustText import adjust_text
from analysis.station_basins import initial_rule
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator
from rasterio.transform import Affine
from shapely.geometry.base import BaseGeometry

OUTPUT_DIRECTORY = initial_rule.OUTPUT_DIRECTORY / "sensitivity"
CHARTS_DIRECTORY = OUTPUT_DIRECTORY / "charts"
COUNTRY_FIGURES_DIRECTORY = OUTPUT_DIRECTORY / "countries"
MASK_CACHE_DIRECTORY = initial_rule.CACHE_DIRECTORY / "country-masks"

LARGE_UNIT_KM2 = 20_000
SMALL_UNIT_KM2 = initial_rule.MIN_BASIN_AREA_KM2
SQUARE_METRES_PER_KM2 = 1_000_000

BASELINE_START_LEVEL = initial_rule.MIN_LEVEL
BASELINE_MAX_AREA_KM2 = initial_rule.MAX_BASIN_AREA_KM2
START_LEVELS = [4, 5, 6, 7, 8, 9]
AREA_CAPS_KM2: list[float | None] = [5_000, 10_000, 20_000, 50_000, 100_000, None]
MINIMUM_AREAS_KM2 = [0, 100, 250, 500, 1_000, 2_500]
SHARED_LEVELS = [5, 6, 7, 8, 9]
TRACE_LEVELS = [7, 8, 10, 12]
TRACE_DISTANCES_KM = [0, 50, 100, 200, 300, 500]

# The rules shown side by side in the country figures: the PR rule as it is, and
# the candidate that follows from the sensitivity analysis.
BASELINE_RULE = f"alone, start level {BASELINE_START_LEVEL}"
CANDIDATE_RULE = "downstream 200 km, level 7"
COUNTRY_FIGURE_RULES: dict[str, str] = {
    BASELINE_RULE: "PR rule: largest basin with the station alone",
    CANDIDATE_RULE: "Candidate: level-7 polygon plus 200 km downstream",
}

# A polygon is one HydroBASINS polygon: (level, HYBAS_ID). A unit is the area
# mapped to a station: one polygon, or a chain of polygons along the river.
Polygon = tuple[int, int]
Unit = tuple[Polygon, ...]


class RuleKind(StrEnum):
    LARGEST_ALONE = "largest_alone"
    FIXED_LEVEL = "fixed_level"
    DOWNSTREAM_TRACE = "downstream_trace"


class Dimension(StrEnum):
    START_LEVEL = "start_level"
    AREA_CAP = "area_cap"
    MINIMUM_AREA = "minimum_area"
    STATION_SCOPE = "station_scope"
    COASTAL_UNITS = "coastal_units"
    UNIQUENESS = "uniqueness"
    DOWNSTREAM = "downstream"


@dataclass(frozen=True)
class Rule:
    name: str
    dimension: Dimension
    series: str
    parameter: str
    kind: RuleKind = RuleKind.LARGEST_ALONE
    # LARGEST_ALONE: the PR rule.
    start_level: int = BASELINE_START_LEVEL
    max_area_km2: float | None = BASELINE_MAX_AREA_KM2
    minimum_area_km2: float = 0
    count_all_countries: bool = False
    exclude_coastal: bool = False
    # FIXED_LEVEL and DOWNSTREAM_TRACE.
    level: int = 0
    distance_km: float = 0


@dataclass
class Location:
    hybas_id: int
    sub_area_km2: float
    coastal: bool


@dataclass
class Context:
    countries: dict[str, initial_rule.CountryInputs]
    station_country: dict[str, str]
    # (station code, level) -> the polygon holding the station at that level
    locations: dict[tuple[str, int], Location]
    # polygon -> the stations inside it
    occupants: dict[Polygon, list[str]]
    # level -> basins indexed by HYBAS_ID
    basins: dict[int, gpd.GeoDataFrame]


@dataclass
class CountryRasters:
    """Everything on the grid of the country's flood map."""

    transform: Affine
    pixel_area_km2: np.ndarray  # one value per row
    in_country: np.ndarray
    flooded: np.ndarray  # flood map inside the country
    in_today: np.ndarray  # inside any current footprint
    # station code -> (rows, columns, mask) of its current footprint
    footprints: dict[str, tuple[slice, slice, np.ndarray]]
    polygon_masks: dict[Polygon, tuple[slice, slice, np.ndarray] | None] = field(
        default_factory=dict
    )


def main() -> None:
    CHARTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    COUNTRY_FIGURES_DIRECTORY.mkdir(parents=True, exist_ok=True)
    parser = argparse.ArgumentParser(description=__doc__)
    initial_rule.add_input_arguments(parser)
    arguments = parser.parse_args()
    seed_repository_root = initial_rule.get_seed_repository_root(arguments)
    initial_rule.extract_basin_shapefiles(arguments.basins_dir)
    context = _build_context(seed_repository_root, arguments.basins_dir)
    rules = _define_rules()
    assignments = {rule.name: _assign(rule, context, True) for rule in rules}
    assignments_alone = {rule.name: _assign(rule, context, False) for rule in rules}

    station_rows: list[dict] = []
    country_rows: list[dict] = []
    for country in context.countries.values():
        rasters = _build_country_rasters(country, seed_repository_root)
        for rule in rules:
            station_rows.extend(
                _measure_stations(
                    rule,
                    country,
                    context,
                    rasters,
                    assignments[rule.name],
                    assignments_alone[rule.name],
                )
            )
            country_rows.append(
                _measure_country(
                    rule, country, context, rasters, assignments[rule.name]
                )
            )
        _plot_country_comparison(
            country,
            context,
            rasters,
            {name: assignments[name] for name in COUNTRY_FIGURE_RULES},
            {
                row["rule"]: row
                for row in country_rows
                if row["country"] == country.country_code
                and row["rule"] in COUNTRY_FIGURE_RULES
            },
        )
        print(f"{country.country_code}: measured {len(rules)} rules")

    per_station = pd.DataFrame(station_rows)
    per_country = pd.DataFrame(country_rows)
    per_rule = _summarise_rules(rules, per_station, per_country)
    per_station.round(4).to_csv(OUTPUT_DIRECTORY / "per_station.csv", index=False)
    per_country.round(4).to_csv(OUTPUT_DIRECTORY / "per_country.csv", index=False)
    per_rule.round(4).to_csv(OUTPUT_DIRECTORY / "per_rule.csv", index=False)
    for dimension in Dimension:
        _plot_dimension(dimension, per_rule)
    _plot_trade_off(per_rule)
    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 30)
    pd.set_option("display.max_rows", 200)
    print(per_rule.drop(columns=["dimension"]).round(2).to_string(index=False))


# --- Rules --------------------------------------------------------------------


def _define_rules() -> list[Rule]:
    rules: list[Rule] = []
    for start_level in START_LEVELS:
        rules.append(
            Rule(
                name=f"alone, start level {start_level}",
                dimension=Dimension.START_LEVEL,
                series="PR rule",
                parameter=str(start_level),
                start_level=start_level,
            )
        )
    for area_cap in AREA_CAPS_KM2:
        label = "none" if area_cap is None else f"{area_cap:,.0f}"
        rules.append(
            Rule(
                name=f"alone, area cap {label}",
                dimension=Dimension.AREA_CAP,
                series="PR rule",
                parameter=label,
                max_area_km2=area_cap,
            )
        )
    for minimum_area in MINIMUM_AREAS_KM2:
        rules.append(
            Rule(
                name=f"alone, minimum area {minimum_area:,}",
                dimension=Dimension.MINIMUM_AREA,
                series="PR rule",
                parameter=f"{minimum_area:,}",
                minimum_area_km2=minimum_area,
            )
        )
    for count_all_countries in (False, True):
        label = "all seven countries" if count_all_countries else "own country"
        rules.append(
            Rule(
                name=f"alone, other stations of {label}",
                dimension=Dimension.STATION_SCOPE,
                series="PR rule",
                parameter=label,
                count_all_countries=count_all_countries,
            )
        )
    for exclude_coastal in (False, True):
        label = "excluded" if exclude_coastal else "allowed"
        rules.append(
            Rule(
                name=f"alone, lumped coastal units {label}",
                dimension=Dimension.COASTAL_UNITS,
                series="PR rule",
                parameter=label,
                exclude_coastal=exclude_coastal,
            )
        )
    for level in SHARED_LEVELS:
        rules.append(
            Rule(
                name=f"alone from level {level}",
                dimension=Dimension.UNIQUENESS,
                series="station must be alone (PR rule from this level)",
                parameter=str(level),
                start_level=level,
            )
        )
        rules.append(
            Rule(
                name=f"shared, fixed level {level}",
                dimension=Dimension.UNIQUENESS,
                series="stations may share (fixed level)",
                parameter=str(level),
                kind=RuleKind.FIXED_LEVEL,
                level=level,
            )
        )
    for level in TRACE_LEVELS:
        for distance_km in TRACE_DISTANCES_KM:
            rules.append(
                Rule(
                    name=f"downstream {distance_km} km, level {level}",
                    dimension=Dimension.DOWNSTREAM,
                    series=f"level {level} polygons",
                    parameter=str(distance_km),
                    kind=RuleKind.DOWNSTREAM_TRACE,
                    level=level,
                    distance_km=distance_km,
                )
            )
    return rules


def _assign(
    rule: Rule, context: Context, consider_other_stations: bool
) -> dict[str, Unit | None]:
    """The unit of every station. With `consider_other_stations` off, each station
    is treated as if it were the only one: the difference shows the dependence."""
    return {
        station_code: _assign_station(
            rule, context, station_code, consider_other_stations
        )
        for station_code in context.station_country
    }


def _assign_station(
    rule: Rule, context: Context, station_code: str, consider_other_stations: bool
) -> Unit | None:
    if rule.kind == RuleKind.FIXED_LEVEL:
        location = context.locations.get((station_code, rule.level))
        return None if location is None else ((rule.level, location.hybas_id),)
    if rule.kind == RuleKind.DOWNSTREAM_TRACE:
        return _trace_downstream(rule, context, station_code, consider_other_stations)

    for level in range(rule.start_level, initial_rule.MAX_LEVEL + 1):
        location = context.locations.get((station_code, level))
        if location is None:
            continue
        if rule.max_area_km2 is not None and location.sub_area_km2 > rule.max_area_km2:
            continue
        if rule.exclude_coastal and location.coastal:
            continue
        if consider_other_stations and _other_stations(
            context, station_code, (level, location.hybas_id), rule.count_all_countries
        ):
            continue
        if location.sub_area_km2 < rule.minimum_area_km2:
            return None
        return ((level, location.hybas_id),)
    return None


def _other_stations(
    context: Context, station_code: str, polygon: Polygon, count_all_countries: bool
) -> list[str]:
    own_country = context.station_country[station_code]
    return [
        other
        for other in context.occupants.get(polygon, [])
        if other != station_code
        and (count_all_countries or context.station_country[other] == own_country)
    ]


def _trace_downstream(
    rule: Rule, context: Context, station_code: str, stop_at_stations: bool
) -> Unit | None:
    """The station's own polygon plus the polygons downstream of it, until the
    distance limit, the next station, the river's end or the edge of the data."""
    location = context.locations.get((station_code, rule.level))
    if location is None:
        return None
    basins = context.basins[rule.level]
    start = location.hybas_id
    chain = [start]
    current = int(basins.at[start, "NEXT_DOWN"])
    while (
        current != 0
        and current in basins.index
        and basins.at[start, "DIST_SINK"] - basins.at[current, "DIST_SINK"]
        <= rule.distance_km
        and not (stop_at_stations and context.occupants.get((rule.level, current)))
    ):
        chain.append(current)
        current = int(basins.at[current, "NEXT_DOWN"])
    return tuple((rule.level, hybas_id) for hybas_id in chain)


# --- Inputs -------------------------------------------------------------------


def _build_context(seed_root: Path, basins_directory: Path) -> Context:
    countries = {
        code: initial_rule.load_country_inputs(seed_root, code)
        for code in initial_rule.COUNTRIES
    }
    merged = initial_rule.merge_basins(
        [
            initial_rule.load_basins(country, basins_directory)
            for country in countries.values()
        ]
    )
    stations = gpd.GeoDataFrame(
        pd.concat([country.stations for country in countries.values()]),
        crs=initial_rule.GEOGRAPHIC_CRS,
    ).reset_index(drop=True)

    locations: dict[tuple[str, int], Location] = {}
    occupants: dict[Polygon, list[str]] = {}
    for level, basins in merged.items():
        joined = gpd.sjoin(
            stations,
            basins[["HYBAS_ID", "SUB_AREA", "COAST", "geometry"]],
            how="inner",
            predicate="within",
        )
        for row in joined.itertuples():
            hybas_id = int(row.HYBAS_ID)
            locations[(row.stationCode, level)] = Location(
                hybas_id, float(row.SUB_AREA), bool(row.COAST)
            )
            occupants.setdefault((level, hybas_id), []).append(row.stationCode)
    return Context(
        countries=countries,
        station_country=dict(
            zip(stations["stationCode"], stations["country"], strict=True)
        ),
        locations=locations,
        occupants=occupants,
        basins={
            level: basins.set_index("HYBAS_ID") for level, basins in merged.items()
        },
    )


def _build_country_rasters(
    country: initial_rule.CountryInputs, seed_repository_root: Path
) -> CountryRasters:
    flood_map = initial_rule.load_flood_map(seed_repository_root, country.country_code)
    shape = flood_map.flooded.shape
    in_country = _cached_mask(
        f"{country.country_code}_in_country",
        country.outline,
        shape,
        flood_map.transform,
    )
    footprints = [
        footprint for footprint in country.footprints.values() if footprint is not None
    ]
    in_today = _cached_mask(
        f"{country.country_code}_in_today",
        shapely.union_all(footprints),
        shape,
        flood_map.transform,
    )
    rasters = CountryRasters(
        transform=flood_map.transform,
        pixel_area_km2=initial_rule.pixel_areas_km2(flood_map.transform, shape[0]),
        in_country=in_country,
        flooded=flood_map.flooded & in_country,
        in_today=in_today & in_country,
        footprints={},
    )
    for station_code, footprint in country.footprints.items():
        if footprint is not None:
            window = _rasterise(footprint, rasters)
            if window is not None:
                rasters.footprints[station_code] = window
    return rasters


def _cached_mask(
    name: str, geometry: BaseGeometry, shape: tuple[int, int], transform: Affine
) -> np.ndarray:
    MASK_CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    cache_path = MASK_CACHE_DIRECTORY / f"{name}.npz"
    if cache_path.exists():
        return np.load(cache_path)["mask"]
    mask = rasterio.features.geometry_mask(
        [geometry], out_shape=shape, transform=transform, invert=True
    )
    np.savez_compressed(cache_path, mask=mask)
    return mask


def _rasterise(
    geometry: BaseGeometry, rasters: CountryRasters
) -> tuple[slice, slice, np.ndarray] | None:
    """The geometry as a mask on the country grid, limited to its bounding box."""
    min_x, min_y, max_x, max_y = geometry.bounds
    transform = rasters.transform
    height, width = rasters.in_country.shape
    column_start = max(0, int(np.floor((min_x - transform.c) / transform.a)))
    column_stop = min(width, int(np.ceil((max_x - transform.c) / transform.a)))
    row_start = max(0, int(np.floor((max_y - transform.f) / transform.e)))
    row_stop = min(height, int(np.ceil((min_y - transform.f) / transform.e)))
    if column_stop <= column_start or row_stop <= row_start:
        return None
    mask = rasterio.features.geometry_mask(
        [geometry],
        out_shape=(row_stop - row_start, column_stop - column_start),
        transform=transform * Affine.translation(column_start, row_start),
        invert=True,
    )
    return slice(row_start, row_stop), slice(column_start, column_stop), mask


# --- Measuring ----------------------------------------------------------------


def _measure_stations(
    rule: Rule,
    country: initial_rule.CountryInputs,
    context: Context,
    rasters: CountryRasters,
    assignment: dict[str, Unit | None],
    assignment_alone: dict[str, Unit | None],
) -> list[dict]:
    rows: list[dict] = []
    for station_code in country.stations["stationCode"]:
        unit = assignment[station_code]
        footprint = rasters.footprints.get(station_code)
        row: dict = {
            "rule": rule.name,
            "country": country.country_code,
            "station_code": station_code,
            "has_unit": unit is not None,
            "footprint_area_km2": np.nan,
            "flooded_in_footprint_km2": np.nan,
        }
        if footprint is not None:
            rows_slice, columns_slice, mask = footprint
            row["footprint_area_km2"] = _area_km2(mask, rows_slice, rasters)
            row["flooded_in_footprint_km2"] = _area_km2(
                mask & rasters.flooded[rows_slice, columns_slice], rows_slice, rasters
            )
        if unit is not None:
            in_country = in_footprint = flooded = flooded_in_footprint = 0.0
            for polygon in unit:
                window = _polygon_window(polygon, context, rasters)
                if window is None:
                    continue
                rows_slice, columns_slice, mask = window
                in_country += _area_km2(
                    mask & rasters.in_country[rows_slice, columns_slice],
                    rows_slice,
                    rasters,
                )
                flooded += _area_km2(
                    mask & rasters.flooded[rows_slice, columns_slice],
                    rows_slice,
                    rasters,
                )
                if footprint is not None:
                    overlap = _overlap(window, footprint)
                    if overlap is not None:
                        overlap_rows, overlap_columns, overlap_mask = overlap
                        in_footprint += _area_km2(overlap_mask, overlap_rows, rasters)
                        flooded_in_footprint += _area_km2(
                            overlap_mask
                            & rasters.flooded[overlap_rows, overlap_columns],
                            overlap_rows,
                            rasters,
                        )
            polygon_area = sum(_polygon_area_km2(polygon, context) for polygon in unit)
            row.update(
                {
                    "unit_level": unit[0][0],
                    "unit_polygon_count": len(unit),
                    "unit_area_km2": sum(
                        float(context.basins[level].at[hybas_id, "SUB_AREA"])
                        for level, hybas_id in unit
                    ),
                    "unit_share_outside_country": max(
                        0.0, 1 - in_country / polygon_area
                    ),
                    "depends_on_other_stations": unit != assignment_alone[station_code],
                    "flooded_in_unit_km2": flooded,
                }
            )
            if footprint is not None:
                row["share_of_footprint_in_unit"] = (
                    in_footprint / row["footprint_area_km2"]
                )
                row["flooded_in_both_km2"] = flooded_in_footprint
        rows.append(row)
    return rows


def _measure_country(
    rule: Rule,
    country: initial_rule.CountryInputs,
    context: Context,
    rasters: CountryRasters,
    assignment: dict[str, Unit | None],
) -> dict:
    """Numbers for all units of the country together. Polygons of one rule do not
    overlap unless they are the same polygon, so each distinct polygon counts once."""
    polygons = {
        polygon
        for station_code in country.stations["stationCode"]
        for polygon in assignment[station_code] or ()
    }
    covered = flooded = flooded_in_today = 0.0
    for polygon in polygons:
        window = _polygon_window(polygon, context, rasters)
        if window is None:
            continue
        rows_slice, columns_slice, mask = window
        covered += _area_km2(
            mask & rasters.in_country[rows_slice, columns_slice], rows_slice, rasters
        )
        flooded_mask = mask & rasters.flooded[rows_slice, columns_slice]
        flooded += _area_km2(flooded_mask, rows_slice, rasters)
        flooded_in_today += _area_km2(
            flooded_mask & rasters.in_today[rows_slice, columns_slice],
            rows_slice,
            rasters,
        )
    everything = slice(0, rasters.in_country.shape[0])
    return {
        "rule": rule.name,
        "country": country.country_code,
        "country_area_km2": _area_km2(rasters.in_country, everything, rasters),
        "covered_today_km2": _area_km2(rasters.in_today, everything, rasters),
        "covered_by_units_km2": covered,
        "flood_map_km2": _area_km2(rasters.flooded, everything, rasters),
        "flooded_covered_today_km2": _area_km2(
            rasters.flooded & rasters.in_today, everything, rasters
        ),
        "flooded_covered_by_units_km2": flooded,
        "flooded_covered_by_both_km2": flooded_in_today,
    }


def _polygon_window(
    polygon: Polygon, context: Context, rasters: CountryRasters
) -> tuple[slice, slice, np.ndarray] | None:
    if polygon not in rasters.polygon_masks:
        level, hybas_id = polygon
        rasters.polygon_masks[polygon] = _rasterise(
            context.basins[level].at[hybas_id, "geometry"], rasters
        )
    return rasters.polygon_masks[polygon]


def _polygon_area_km2(polygon: Polygon, context: Context) -> float:
    level, hybas_id = polygon
    area_square_metres, _ = initial_rule.GEOD.geometry_area_perimeter(
        context.basins[level].at[hybas_id, "geometry"]
    )
    return abs(area_square_metres) / SQUARE_METRES_PER_KM2


def _overlap(
    first: tuple[slice, slice, np.ndarray], second: tuple[slice, slice, np.ndarray]
) -> tuple[slice, slice, np.ndarray] | None:
    """Where two windowed masks are both set, as a windowed mask."""
    first_rows, first_columns, first_mask = first
    second_rows, second_columns, second_mask = second
    row_start = max(first_rows.start, second_rows.start)
    row_stop = min(first_rows.stop, second_rows.stop)
    column_start = max(first_columns.start, second_columns.start)
    column_stop = min(first_columns.stop, second_columns.stop)
    if row_stop <= row_start or column_stop <= column_start:
        return None
    both = (
        first_mask[
            row_start - first_rows.start : row_stop - first_rows.start,
            column_start - first_columns.start : column_stop - first_columns.start,
        ]
        & second_mask[
            row_start - second_rows.start : row_stop - second_rows.start,
            column_start - second_columns.start : column_stop - second_columns.start,
        ]
    )
    return slice(row_start, row_stop), slice(column_start, column_stop), both


def _area_km2(mask: np.ndarray, rows: slice, rasters: CountryRasters) -> float:
    return float((mask.sum(axis=1) * rasters.pixel_area_km2[rows]).sum())


# --- Summary per rule -----------------------------------------------------------


def _summarise_rules(
    rules: list[Rule], per_station: pd.DataFrame, per_country: pd.DataFrame
) -> pd.DataFrame:
    summaries: list[dict] = []
    for rule in rules:
        stations = per_station[per_station["rule"] == rule.name]
        countries = per_country[per_country["rule"] == rule.name]
        areas = stations["unit_area_km2"].dropna()
        summaries.append(
            {
                "dimension": rule.dimension.value,
                "series": rule.series,
                "parameter": rule.parameter,
                "rule": rule.name,
                "stations_with_unit": int(stations["has_unit"].sum()),
                "median_unit_area_km2": areas.median(),
                "largest_unit_area_km2": areas.max(),
                "units_over_20000_km2": int((areas > LARGE_UNIT_KM2).sum()),
                "units_under_100_km2": int((areas < SMALL_UNIT_KM2).sum()),
                "units_over_1_percent_outside_country": int(
                    (
                        stations["unit_share_outside_country"]
                        > initial_rule.OUTSIDE_COUNTRY_SHARE_THRESHOLD
                    ).sum()
                ),
                "stations_depending_on_other_stations": int(
                    stations["depends_on_other_stations"].fillna(False).sum()
                ),
                "median_share_of_footprint_in_unit": stations[
                    "share_of_footprint_in_unit"
                ].median(),
                # Station by station: is today's flooded area in that station's unit?
                "station_flooded_area_kept": stations["flooded_in_both_km2"].sum()
                / stations["flooded_in_footprint_km2"].sum(),
                # Country-wide: is today's flooded area in any station's unit?
                "country_flooded_area_kept": countries[
                    "flooded_covered_by_both_km2"
                ].sum()
                / countries["flooded_covered_today_km2"].sum(),
                "share_of_flood_map_in_units": countries[
                    "flooded_covered_by_units_km2"
                ].sum()
                / countries["flood_map_km2"].sum(),
                "share_of_flood_map_in_footprints_today": countries[
                    "flooded_covered_today_km2"
                ].sum()
                / countries["flood_map_km2"].sum(),
                "share_of_land_in_units": countries["covered_by_units_km2"].sum()
                / countries["country_area_km2"].sum(),
                "share_of_land_in_footprints_today": countries[
                    "covered_today_km2"
                ].sum()
                / countries["country_area_km2"].sum(),
            }
        )
    return pd.DataFrame(summaries)


# --- Charts -------------------------------------------------------------------

DIMENSION_TITLES: dict[Dimension, tuple[str, str]] = {
    Dimension.START_LEVEL: (
        "Start level: the coarsest HydroBASINS level the rule may pick",
        "Start level (4 is the PR rule)",
    ),
    Dimension.AREA_CAP: (
        "Area cap: the largest basin the rule may pick",
        "Area cap in km² (50,000 is the PR rule)",
    ),
    Dimension.MINIMUM_AREA: (
        "Minimum area: drop a station whose basin is smaller",
        "Minimum area in km² (0 is the PR rule, 100 is the proposal)",
    ),
    Dimension.STATION_SCOPE: (
        'Station scope: which other stations count for "alone"',
        "Other stations counted",
    ),
    Dimension.COASTAL_UNITS: (
        "Lumped coastal units: allow or exclude them",
        "Lumped coastal units (HydroBASINS COAST = 1)",
    ),
    Dimension.UNIQUENESS: (
        "Uniqueness: must a station be alone in its basin?",
        "HydroBASINS level",
    ),
    Dimension.DOWNSTREAM: (
        "Direction: add the polygons downstream of the station",
        "Distance followed downstream in km (0 is the station's own polygon)",
    ),
}
PANELS: list[tuple[str, str, bool]] = [
    ("median_unit_area_km2", "Median unit area (km²)", False),
    ("largest_unit_area_km2", "Largest unit area (km²)", False),
    (
        "stations_without_usable_unit",
        "Stations with no unit or one under 100 km²",
        False,
    ),
    (
        "stations_depending_on_other_stations",
        "Stations whose unit depends on other stations",
        False,
    ),
    (
        "country_flooded_area_kept",
        "Flooded area covered today that stays covered",
        True,
    ),
    ("share_of_flood_map_in_units", "Share of the whole flood map inside a unit", True),
]
SERIES_COLOURS = ["#0b5cad", "#d1495b", "#2e933c", "#8a6d1c"]
COUNT_COLUMNS = {"stations_without_usable_unit", "stations_depending_on_other_stations"}


def _plot_dimension(dimension: Dimension, per_rule: pd.DataFrame) -> None:
    per_rule = per_rule.assign(
        stations_without_usable_unit=sum(initial_rule.EXPECTED_STATION_COUNTS.values())
        - per_rule["stations_with_unit"]
        + per_rule["units_under_100_km2"]
    )
    rules = per_rule[per_rule["dimension"] == dimension.value]
    baseline = per_rule[per_rule["rule"] == BASELINE_RULE].iloc[0]
    title, x_label = DIMENSION_TITLES[dimension]

    figure, axes_grid = plt.subplots(
        2, 3, figsize=initial_rule.FIGURE_SIZE_INCHES, dpi=initial_rule.FIGURE_DPI
    )
    figure.suptitle(title, x=0.02, y=0.975, ha="left", fontsize=17, fontweight="bold")
    for axes, (column, panel_title, is_share) in zip(
        axes_grid.flat, PANELS, strict=True
    ):
        for (series, series_rules), colour in zip(
            rules.groupby("series", sort=False), SERIES_COLOURS, strict=False
        ):
            axes.plot(
                series_rules["parameter"],
                series_rules[column],
                marker="o",
                linewidth=2,
                color=colour,
                label=series,
            )
        axes.axhline(
            baseline[column],
            color="#606060",
            linewidth=1,
            linestyle=(0, (4, 3)),
            label="PR rule as it is",
        )
        if column == "share_of_flood_map_in_units":
            axes.axhline(
                baseline["share_of_flood_map_in_footprints_today"],
                color="#8a6d1c",
                linewidth=1,
                linestyle=(0, (1, 2)),
                label="today's footprints",
            )
        axes.set_title(panel_title, fontsize=12, loc="left")
        axes.set_ylim(bottom=0)
        if is_share:
            axes.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
        else:
            axes.yaxis.set_major_formatter(lambda value, _: f"{value:,.0f}")
        if column in COUNT_COLUMNS:
            axes.yaxis.set_major_locator(MaxNLocator(integer=True))
        axes.tick_params(labelsize=9)
        axes.grid(axis="y", color="#e0e0e0", linewidth=0.8)
        axes.spines[["top", "right"]].set_visible(False)
        axes.set_xlabel(x_label, fontsize=9.5)
    handles, labels = axes_grid.flat[-1].get_legend_handles_labels()
    figure.legend(
        handles,
        labels,
        loc="lower left",
        bbox_to_anchor=(0.02, 0.005),
        ncols=len(labels),
        fontsize=11,
        frameon=False,
    )
    figure.tight_layout(rect=(0, 0.05, 1, 0.94))
    path: Path = CHARTS_DIRECTORY / f"{dimension.value}.png"
    figure.savefig(path)
    plt.close(figure)
    print(f"Wrote {path}")


# Families of rules drawn as one line each in the trade-off chart:
# (label, dimension, series or None for all, colour).
TRADE_OFF_FAMILIES: list[tuple[str, Dimension, str | None, str]] = [
    ("PR rule, start level 4 to 9", Dimension.START_LEVEL, None, "#606060"),
    ("PR rule, area cap 5,000 km² to none", Dimension.AREA_CAP, None, "#b0b0b0"),
    (
        "Fixed level 5 to 9, stations may share",
        Dimension.UNIQUENESS,
        "stations may share (fixed level)",
        "#d1495b",
    ),
    (
        "Level-7 polygons, 0 to 500 km downstream",
        Dimension.DOWNSTREAM,
        "level 7 polygons",
        "#0b5cad",
    ),
    (
        "Level-8 polygons, 0 to 500 km downstream",
        Dimension.DOWNSTREAM,
        "level 8 polygons",
        "#2e933c",
    ),
    (
        "Level-12 polygons, 0 to 500 km downstream",
        Dimension.DOWNSTREAM,
        "level 12 polygons",
        "#8a6d1c",
    ),
]


def _plot_trade_off(per_rule: pd.DataFrame) -> None:
    """Every variant on two axes: how much land it maps to stations, and how much
    of the flooded area covered today it keeps."""
    figure, axes = plt.subplots(
        figsize=initial_rule.FIGURE_SIZE_INCHES, dpi=initial_rule.FIGURE_DPI
    )
    figure.suptitle(
        "All variants: land mapped to stations against today's flooded area kept",
        x=0.02,
        y=0.975,
        ha="left",
        fontsize=17,
        fontweight="bold",
    )
    for label, dimension, series, colour in TRADE_OFF_FAMILIES:
        family = per_rule[per_rule["dimension"] == dimension.value]
        if series is not None:
            family = family[family["series"] == series]
        axes.plot(
            family["share_of_land_in_units"],
            family["country_flooded_area_kept"],
            marker="o",
            markersize=5,
            linewidth=1.8,
            color=colour,
            label=label,
        )
        for row in family.iloc[[0, -1]].itertuples():
            axes.annotate(
                row.parameter,
                (row.share_of_land_in_units, row.country_flooded_area_kept),
                xytext=(5, 4),
                textcoords="offset points",
                fontsize=8.5,
                color=colour,
            )
    for rule_name, marker_label, colour in (
        (BASELINE_RULE, "PR rule as it is", "black"),
        (CANDIDATE_RULE, "Candidate: level 7, 200 km downstream", "#0b5cad"),
    ):
        rule = per_rule[per_rule["rule"] == rule_name].iloc[0]
        axes.scatter(
            rule["share_of_land_in_units"],
            rule["country_flooded_area_kept"],
            marker="*",
            s=420,
            color=colour,
            edgecolor="black",
            linewidth=0.8,
            zorder=5,
            label=marker_label,
        )
    today = per_rule["share_of_land_in_footprints_today"].iloc[0]
    axes.axvline(today, color="#8a6d1c", linewidth=1, linestyle=(0, (1, 2)))
    axes.annotate(
        f"Today's footprints: {today:.0%} of the land,\n100% kept by definition",
        (today, 0.02),
        xytext=(6, 0),
        textcoords="offset points",
        fontsize=10,
        color="#8a6d1c",
    )
    axes.set_xlabel(
        "Share of the land of the seven countries mapped to a station", fontsize=12
    )
    axes.set_ylabel(
        "Share of the flooded area covered today that stays covered", fontsize=12
    )
    axes.xaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    axes.yaxis.set_major_formatter(lambda value, _: f"{value:.0%}")
    axes.set_xlim(0, 0.45)
    axes.set_ylim(0, 0.75)
    axes.grid(color="#e0e0e0", linewidth=0.8)
    axes.spines[["top", "right"]].set_visible(False)
    axes.legend(loc="lower right", fontsize=11, frameon=False)
    figure.tight_layout(rect=(0, 0, 1, 0.94))
    path = CHARTS_DIRECTORY / "trade_off.png"
    figure.savefig(path)
    plt.close(figure)
    print(f"Wrote {path}")


# --- Country figures --------------------------------------------------------------

FLOOD_MAP_COLOUR = "#5b8fc7"
UNIT_FILL_ALPHA = 0.6


def _plot_country_comparison(
    country: initial_rule.CountryInputs,
    context: Context,
    rasters: CountryRasters,
    assignments: dict[str, dict[str, Unit | None]],
    country_rows: dict[str, dict],
) -> None:
    """Today's footprints next to the units of the PR rule and of the candidate."""
    station_codes = list(country.stations["stationCode"])
    colours = initial_rule.station_colours(len(station_codes))
    any_row = next(iter(country_rows.values()))
    panels: list[tuple[str, str, dict[str, BaseGeometry | None]]] = [
        (
            f"Today: admin-area footprints (level {country.admin_level})",
            _describe_coverage(
                any_row["covered_today_km2"] / any_row["country_area_km2"],
                any_row["flooded_covered_today_km2"] / any_row["flood_map_km2"],
                None,
            ),
            dict(country.footprints),
        )
    ]
    for rule_name, panel_title in COUNTRY_FIGURE_RULES.items():
        row = country_rows[rule_name]
        panels.append(
            (
                panel_title,
                _describe_coverage(
                    row["covered_by_units_km2"] / row["country_area_km2"],
                    row["flooded_covered_by_units_km2"] / row["flood_map_km2"],
                    row["flooded_covered_by_both_km2"]
                    / row["flooded_covered_today_km2"],
                ),
                {
                    station_code: _unit_geometry(unit, context)
                    for station_code, unit in assignments[rule_name].items()
                    if station_code in station_codes
                },
            )
        )

    figure = plt.figure(
        figsize=initial_rule.FIGURE_SIZE_INCHES, dpi=initial_rule.FIGURE_DPI
    )
    figure.suptitle(
        f"{country.country_name}: today's footprints, the PR rule and the candidate",
        x=0.02,
        y=0.975,
        ha="left",
        fontsize=17,
        fontweight="bold",
    )
    outline = country.outline.simplify(initial_rule.PLOT_SIMPLIFY_TOLERANCE_DEGREES)
    bounds = shapely.union_all(
        [country.outline.envelope, *country.stations.geometry]
    ).bounds
    panel_width = 0.96 / len(panels)
    for index, (title, statistics, areas) in enumerate(panels):
        axes = figure.add_axes(
            (0.02 + index * panel_width, 0.09, panel_width - 0.012, 0.73)
        )
        initial_rule.plot_geometry(
            axes,
            outline,
            facecolor=initial_rule.UNCOVERED_LAND_COLOUR,
            edgecolor="none",
            zorder=1,
        )
        initial_rule.fit_extent(axes, bounds)
        limits = (*axes.get_xlim(), *axes.get_ylim())
        initial_rule.show_mask(
            axes, rasters.flooded, rasters.transform, FLOOD_MAP_COLOUR, zorder=2
        )
        for station_code, colour in zip(station_codes, colours, strict=True):
            area = areas.get(station_code)
            if area is not None:
                initial_rule.plot_geometry(
                    axes,
                    area.simplify(initial_rule.PLOT_SIMPLIFY_TOLERANCE_DEGREES),
                    facecolor=(*colour, UNIT_FILL_ALPHA),
                    edgecolor=initial_rule.darken(colour, 0.7),
                    linewidth=0.6,
                    zorder=3,
                )
        initial_rule.plot_geometry(
            axes,
            outline,
            facecolor="none",
            edgecolor="black",
            linewidth=0.8,
            zorder=4,
        )
        _plot_stations(axes, country, station_codes, colours)
        axes.set_xlim(limits[0], limits[1])
        axes.set_ylim(limits[2], limits[3])
        axes.set_xticks([])
        axes.set_yticks([])
        axes.set_xlabel("")
        axes.set_ylabel("")
        axes.set_title(f"{title}\n{statistics}", fontsize=10.5, loc="left")
    figure.legend(
        handles=[
            Patch(
                facecolor="#7fa8d0",
                alpha=UNIT_FILL_ALPHA,
                edgecolor="#40607c",
                label="Area mapped to a station (one colour per station)",
            ),
            Patch(
                facecolor=FLOOD_MAP_COLOUR,
                label=f"{initial_rule.FLOOD_RETURN_PERIOD_YEARS}-year flood map",
            ),
            Patch(
                facecolor=initial_rule.UNCOVERED_LAND_COLOUR,
                edgecolor="black",
                label="Land mapped to no station",
            ),
            Line2D(
                [],
                [],
                marker="o",
                linestyle="none",
                markersize=7,
                markerfacecolor="#7fa8d0",
                markeredgecolor="black",
                label="GloFAS station",
            ),
        ],
        loc="lower left",
        bbox_to_anchor=(0.015, 0.005),
        ncols=4,
        fontsize=11,
        frameon=False,
    )
    path = COUNTRY_FIGURES_DIRECTORY / f"{country.country_code}_comparison.png"
    figure.savefig(path)
    plt.close(figure)
    print(f"Wrote {path}")


def _describe_coverage(
    land_share: float, flood_map_share: float, kept_share: float | None
) -> str:
    description = (
        f"{land_share:.0%} of the land, {flood_map_share:.0%} of the flood map"
    )
    if kept_share is None:
        return f"{description}\n"
    return f"{description}\n{kept_share:.0%} of the flooded area covered today is kept"


def _unit_geometry(unit: Unit | None, context: Context) -> BaseGeometry | None:
    if unit is None:
        return None
    return shapely.union_all(
        [context.basins[level].at[hybas_id, "geometry"] for level, hybas_id in unit]
    )


def _plot_stations(
    axes: Axes,
    country: initial_rule.CountryInputs,
    station_codes: list[str],
    colours: list[tuple[float, float, float]],
) -> None:
    points = list(country.stations.geometry)
    axes.scatter(
        [point.x for point in points],
        [point.y for point in points],
        marker="o",
        s=28,
        color=colours,
        edgecolor="black",
        linewidth=0.7,
        zorder=6,
    )
    labels = []
    for station_code, point in zip(station_codes, points, strict=True):
        label = axes.text(
            point.x, point.y, station_code, fontsize=6.5, fontweight="bold", zorder=7
        )
        label.set_path_effects(
            [path_effects.withStroke(linewidth=2, foreground="white")]
        )
        labels.append(label)
    adjust_text(
        labels,
        x=[point.x for point in points],
        y=[point.y for point in points],
        ax=axes,
        expand=(1.2, 1.4),
        arrowprops={"arrowstyle": "-", "color": "black", "linewidth": 0.5},
    )


if __name__ == "__main__":
    main()
