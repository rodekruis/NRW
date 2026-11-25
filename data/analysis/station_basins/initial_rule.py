"""Apply the station-to-basin rule of draft PR #99 to the current GloFAS stations.

Analysis for spike AB#42674. Each station gets the largest HydroBASINS basin that
contains it and no other station. The script writes a map per country, summaries
per station and per country, and before-and-after figures against the 10-year
flood map. See README.md for the inputs.

    uv run python -m analysis.station_basins.initial_rule
"""

import argparse
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.patheffects as path_effects
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio.features
import shapely
from adjustText import adjust_text
from data_management.seed_data_management.admin_areas.admin_area_dataset_helpers import (
    get_feature_geometry,
    get_git_revision,
    get_pcode,
    load_admin_features,
    load_json,
    union_geometries,
)
from matplotlib.axes import Axes
from matplotlib.colors import to_rgb
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from PIL import Image
from pyproj import Geod
from rasterio.transform import Affine
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.geometry.base import BaseGeometry
from shared.data_helpers import get_seed_data_repo_path

DATA_PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIRECTORY = Path(__file__).resolve().parent / "results"
# Rebuildable intermediate files; data/data/ is not tracked.
CACHE_DIRECTORY = DATA_PROJECT_ROOT / "data" / "station_basins"
DEFAULT_BASINS_DIRECTORY = DATA_PROJECT_ROOT / "data" / "hydrobasins"
STATIONS_DIRECTORY = Path("hazard/flood/glofas-stations")
# The source GeoTIFFs (`sources-tif/`) are not committed to the seed repo. The
# data PNGs are the same ~90 m grid with the depth encoded in the RGBA channels.
FLOOD_MAPS_DIRECTORY = Path("hazard/flood/flood-extents/data-png")
FLOOD_MASK_CACHE_DIRECTORY = CACHE_DIRECTORY / "flood-masks"
FLOOD_RETURN_PERIOD_YEARS = 10
AUTHALIC_EARTH_RADIUS_KM = 6371.0072
# Stations shown in the before-and-after figures, and why they were picked.
BEFORE_AFTER_STATIONS: dict[str, str] = {
    "G1074": (
        "Rule joins what the admin areas split. Today's footprint is two parts "
        "35 km apart, and the flooded river stretch between them is left out. The "
        "basin follows the river through both parts."
    ),
    "G1353": (
        "Old and new do not overlap at all. Today's footprint is two parts 95 km "
        "apart, and neither holds the station. The basin lies between the two parts, "
        "around the station."
    ),
    "G5305": (
        "Rule loses the floodplain. Today's footprint follows the lower Tana down "
        "to the delta. The station sits at the downstream end of its basin, and the "
        "next coarser basin is over the area cap, so the lower Tana and the delta "
        "end up in no basin."
    ),
}

# country code -> (HydroBASINS region, flood admin level)
COUNTRIES: dict[str, tuple[str, int]] = {
    "ETH": ("af", 3),
    "KEN": ("af", 3),
    "MWI": ("af", 3),
    # The Philippines is in the Australasia file ("au"), not in the Asia file ("as").
    "PHL": ("au", 3),
    "SSD": ("af", 3),
    "UGA": ("af", 4),
    "ZMB": ("af", 4),
}
EXPECTED_STATION_COUNTS: dict[str, int] = {
    "ETH": 27,
    "ZMB": 20,
    "PHL": 10,
    "UGA": 8,
    "MWI": 4,
    "KEN": 3,
    "SSD": 1,
}

MIN_LEVEL = 4
MAX_LEVEL = 12
MAX_BASIN_AREA_KM2 = 50_000
MIN_BASIN_AREA_KM2 = 100  # proposed addition, not in PR #99
# Share of the basin polygon outside the country outline above which the
# "extends outside the country" flag is set. Below this it is boundary noise.
OUTSIDE_COUNTRY_SHARE_THRESHOLD = 0.01
# Thresholds on (UP_AREA of the level-12 polygon at the station) / (UP_AREA of
# the basin), used to describe where in its basin a station sits. Rough proxies.
DOWNSTREAM_END_SHARE = 0.95
SMALL_TRIBUTARY_SHARE = 0.10

# Admin areas closer than this count as touching (about 100 m), so that slivers
# between neighbouring polygons do not show up as separate footprint parts.
TOUCH_TOLERANCE_DEGREES = 0.001
METRES_PER_KM = 1_000
GEOD = Geod(ellps="WGS84")

CSV_DECIMALS = 4
GEOGRAPHIC_CRS = "EPSG:4326"
EQUAL_AREA_CRS = "EPSG:6933"
SQUARE_METRES_PER_KM2 = 1_000_000
BOUNDING_BOX_PADDING_DEGREES = 0.1
PLOT_SIMPLIFY_TOLERANCE_DEGREES = 0.002
BASIN_COLUMNS = [
    "HYBAS_ID",
    "NEXT_DOWN",
    "MAIN_BAS",
    "SUB_AREA",
    "UP_AREA",
    "PFAF_ID",
    "ENDO",
    "COAST",
    "DIST_SINK",
]

SAME_COUNTRY_SCOPE = "same_country"
ALL_COUNTRIES_SCOPE = "all_countries"
ALL_COUNTRIES_GROUP = "ALL"


@dataclass
class FloodMap:
    flooded: np.ndarray  # boolean, True where the flood depth is above zero
    transform: Affine


@dataclass
class CountryInputs:
    country_code: str
    country_name: str
    region: str
    admin_level: int
    outline: BaseGeometry
    # Outline with interior holes (lakes) filled; used for "outside the country".
    outline_without_holes: BaseGeometry
    stations: gpd.GeoDataFrame
    footprints: dict[str, BaseGeometry | None]
    # Per station: its admin areas grouped into parts that do not touch each other.
    footprint_parts: dict[str, list[BaseGeometry]]
    footprint_part_summaries: dict[str, dict]
    admin_area_counts: dict[str, int]
    missing_pcodes: dict[str, list[str]]


def main() -> None:
    arguments = _parse_arguments()
    seed_repository_root = get_seed_repository_root(arguments)
    basins_directory: Path = arguments.basins_dir
    OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)

    extract_basin_shapefiles(basins_directory)

    countries = {
        country_code: load_country_inputs(seed_repository_root, country_code)
        for country_code in COUNTRIES
    }
    _check_station_counts(countries)

    basins_per_country = {
        country_code: load_basins(country, basins_directory)
        for country_code, country in countries.items()
    }
    all_basins = merge_basins(list(basins_per_country.values()))
    all_stations = pd.concat(
        [country.stations for country in countries.values()], ignore_index=True
    )
    all_stations = gpd.GeoDataFrame(all_stations, crs=GEOGRAPHIC_CRS)

    # Run 1: "no other station" tested per country, exactly as PR #99 does.
    same_country_assignment: dict[str, tuple[int, int]] = {}
    for country_code, country in countries.items():
        stations = country.stations.copy()
        stations["_country"] = country_code
        same_country_assignment.update(
            _find_highest_unique_basin(
                stations, basins_per_country[country_code], MAX_BASIN_AREA_KM2
            )
        )

    # Run 2: "no other station" tested against the stations of all seven countries.
    pooled_stations = all_stations.copy()
    pooled_stations["_country"] = ALL_COUNTRIES_GROUP
    all_countries_assignment = _find_highest_unique_basin(
        pooled_stations, all_basins, MAX_BASIN_AREA_KM2
    )

    locations = _locate_stations(all_stations, all_basins)
    _cross_check_assignment(locations, same_country_assignment, group_by_country=True)
    _cross_check_assignment(locations, all_countries_assignment, group_by_country=False)

    same_country_rows = _describe_stations(
        countries, all_basins, same_country_assignment, locations, True
    )
    all_countries_rows = _describe_stations(
        countries, all_basins, all_countries_assignment, locations, False
    )
    before_after_paths = _analyse_flood_maps(
        countries,
        same_country_rows,
        all_countries_rows,
        seed_repository_root,
        arguments.before_after_stations,
    )
    station_summary = _build_station_summary(same_country_rows, all_countries_rows)
    changed_stations = station_summary[
        station_summary["basin_changes_in_all_countries_run"]
    ]
    country_summary = _build_country_summary(
        countries, same_country_rows, all_countries_rows
    )

    station_summary.round(CSV_DECIMALS).to_csv(
        OUTPUT_DIRECTORY / "station_summary.csv", index=False
    )
    country_summary.round(CSV_DECIMALS).to_csv(
        OUTPUT_DIRECTORY / "country_summary.csv", index=False
    )
    changed_stations[CHANGED_STATION_COLUMNS].round(CSV_DECIMALS).to_csv(
        OUTPUT_DIRECTORY / "changed_stations_all_countries_run.csv", index=False
    )
    separate_parts = station_summary[
        station_summary["current_footprint_part_count"] > 1
    ].sort_values("largest_gap_between_footprint_parts_km", ascending=False)
    separate_parts[SEPARATE_PARTS_COLUMNS].round(CSV_DECIMALS).to_csv(
        OUTPUT_DIRECTORY / "stations_with_separate_footprint_parts.csv", index=False
    )
    _write_station_basins(same_country_rows, "station_basins.geojson")
    _write_station_basins(
        all_countries_rows, "station_basins_all_countries_run.geojson"
    )

    map_paths = _plot_all_maps(
        countries, same_country_rows, all_countries_rows, country_summary
    )
    _write_markdown_summary(
        station_summary,
        country_summary,
        changed_stations,
        separate_parts,
        countries,
        map_paths,
        before_after_paths,
        seed_repository_root,
    )
    print(f"Done. Outputs in {OUTPUT_DIRECTORY}")


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_input_arguments(parser)
    parser.add_argument(
        "--before-after-stations", nargs="*", default=list(BEFORE_AFTER_STATIONS)
    )
    return parser.parse_args()


def add_input_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--seed-repo-root",
        type=Path,
        default=None,
        help="Local clone of the seed repo. Default: SEED_DATA_REPO_ROOT in data/.env.",
    )
    parser.add_argument(
        "--basins-dir",
        type=Path,
        default=DEFAULT_BASINS_DIRECTORY,
        help="Folder with the HydroBASINS archives (see README.md).",
    )


def get_seed_repository_root(arguments: argparse.Namespace) -> Path:
    return arguments.seed_repo_root or Path(get_seed_data_repo_path())


# --- Inputs -----------------------------------------------------------------


def extract_basin_shapefiles(basins_directory: Path) -> None:
    # The .sbn/.sbx spatial indexes in the archives are left out: GDAL rejects them.
    wanted_suffixes = (".shp", ".shx", ".dbf", ".prj")
    for region in sorted({region for region, _ in COUNTRIES.values()}):
        archive_path = basins_directory / f"hybas_{region}_lev01-12_v1c.zip"
        with zipfile.ZipFile(archive_path) as archive:
            for level in range(MIN_LEVEL, MAX_LEVEL + 1):
                for suffix in wanted_suffixes:
                    member = f"hybas_{region}_lev{level:02d}_v1c{suffix}"
                    if not (basins_directory / member).exists():
                        archive.extract(member, basins_directory)


def load_country_inputs(seed_repository_root: Path, country_code: str) -> CountryInputs:
    region, admin_level = COUNTRIES[country_code]
    outline_features = load_admin_features(seed_repository_root, country_code, 0)
    outline = union_geometries(
        [get_feature_geometry(feature) for feature in outline_features]
    )
    if outline is None:
        raise ValueError(f"No country outline for {country_code}")

    station_entries = _load_station_entries(seed_repository_root, country_code)
    stations = gpd.GeoDataFrame(
        {
            "stationCode": [entry["station_code"] for entry in station_entries],
            "station_name": [entry["station_name"] for entry in station_entries],
            "country": country_code,
        },
        geometry=[Point(entry["lon"], entry["lat"]) for entry in station_entries],
        crs=GEOGRAPHIC_CRS,
    )

    admin_geometries = _load_admin_geometries(
        seed_repository_root,
        country_code,
        admin_level,
        {
            pcode
            for entry in station_entries
            for pcode in _get_station_pcodes(entry, admin_level)
        },
    )
    footprints: dict[str, BaseGeometry | None] = {}
    footprint_parts: dict[str, list[BaseGeometry]] = {}
    footprint_part_summaries: dict[str, dict] = {}
    missing_pcodes: dict[str, list[str]] = {}
    for entry in station_entries:
        pcodes = _get_station_pcodes(entry, admin_level)
        station_admin_geometries = [
            admin_geometries[pcode] for pcode in pcodes if pcode in admin_geometries
        ]
        footprints[entry["station_code"]] = union_geometries(station_admin_geometries)
        groups = _group_touching_geometries(station_admin_geometries)
        parts = [shapely.union_all(group) for group in groups]
        footprint_parts[entry["station_code"]] = parts
        footprint_part_summaries[entry["station_code"]] = _summarise_footprint_parts(
            groups, parts
        )
        missing = [pcode for pcode in pcodes if pcode not in admin_geometries]
        if missing:
            missing_pcodes[entry["station_code"]] = missing

    return CountryInputs(
        country_code=country_code,
        country_name=outline_features[0]["properties"]["ADM0_EN"],
        region=region,
        admin_level=admin_level,
        outline=outline,
        outline_without_holes=_fill_holes(outline),
        stations=stations,
        footprints=footprints,
        footprint_parts=footprint_parts,
        footprint_part_summaries=footprint_part_summaries,
        admin_area_counts={
            entry["station_code"]: len(_get_station_pcodes(entry, admin_level))
            for entry in station_entries
        },
        missing_pcodes=missing_pcodes,
    )


def _group_touching_geometries(
    geometries: list[BaseGeometry],
) -> list[list[BaseGeometry]]:
    """Connected groups of geometries, largest group first."""
    group_of = list(range(len(geometries)))

    def find(index: int) -> int:
        while group_of[index] != index:
            group_of[index] = group_of[group_of[index]]
            index = group_of[index]
        return index

    geometry_array = np.array(geometries, dtype=object)
    first_indices, second_indices = shapely.STRtree(geometry_array).query(
        geometry_array, predicate="dwithin", distance=TOUCH_TOLERANCE_DEGREES
    )
    for first, second in zip(first_indices, second_indices, strict=True):
        group_of[find(int(first))] = find(int(second))

    groups: dict[int, list[BaseGeometry]] = {}
    for index, geometry in enumerate(geometries):
        groups.setdefault(find(index), []).append(geometry)
    return sorted(groups.values(), key=len, reverse=True)


def _summarise_footprint_parts(
    groups: list[list[BaseGeometry]], parts: list[BaseGeometry]
) -> dict:
    """Per part, the gap to the nearest other part; the smallest and largest of those."""
    gaps = [
        min(
            _geodesic_gap_km(part, other)
            for other_index, other in enumerate(parts)
            if other_index != index
        )
        for index, part in enumerate(parts)
        if len(parts) > 1
    ]
    return {
        "current_footprint_part_count": len(parts),
        "current_footprint_admin_areas_per_part": "+".join(
            str(len(group)) for group in groups
        ),
        "smallest_gap_between_footprint_parts_km": min(gaps) if gaps else np.nan,
        "largest_gap_between_footprint_parts_km": max(gaps) if gaps else np.nan,
    }


def _geodesic_gap_km(first: BaseGeometry, second: BaseGeometry) -> float:
    (start_x, start_y), (end_x, end_y) = shapely.shortest_line(first, second).coords
    _, _, distance_metres = GEOD.inv(start_x, start_y, end_x, end_y)
    return distance_metres / METRES_PER_KM


def _fill_holes(geometry: BaseGeometry) -> BaseGeometry:
    polygons = [
        Polygon(part.exterior)
        for part in shapely.get_parts(geometry)
        if isinstance(part, Polygon)
    ]
    return shapely.make_valid(MultiPolygon(polygons))


def _load_station_entries(seed_repository_root: Path, country_code: str) -> list[dict]:
    filepath = (
        seed_repository_root
        / STATIONS_DIRECTORY
        / f"{country_code}_station_thresholds.json"
    )
    first_entry_per_code: dict[str, dict] = {}
    for entry in load_json(filepath):
        first_entry_per_code.setdefault(entry["station_code"], entry)
    return list(first_entry_per_code.values())


def _get_station_pcodes(entry: dict, admin_level: int) -> list[str]:
    return entry["pcodes"].get(str(admin_level), [])


def _load_admin_geometries(
    seed_repository_root: Path, country_code: str, admin_level: int, pcodes: set[str]
) -> dict[str, BaseGeometry]:
    features = load_admin_features(seed_repository_root, country_code, admin_level)
    return {
        get_pcode(feature, admin_level): get_feature_geometry(feature)
        for feature in features
        if get_pcode(feature, admin_level) in pcodes
    }


def _check_station_counts(countries: dict[str, CountryInputs]) -> None:
    for country_code, country in countries.items():
        found = len(country.stations)
        expected = EXPECTED_STATION_COUNTS[country_code]
        status = "ok" if found == expected else "MISMATCH"
        print(f"{country_code}: {found} stations (expected {expected}) {status}")
    all_codes = [
        code
        for country in countries.values()
        for code in country.stations["stationCode"]
    ]
    if len(all_codes) != len(set(all_codes)):
        raise ValueError("Station codes are not unique across countries")


def load_basins(
    country: CountryInputs, basins_directory: Path
) -> dict[int, gpd.GeoDataFrame]:
    """Read each level with a bounding box around the country and its stations."""
    min_x, min_y, max_x, max_y = shapely.union_all(
        [country.outline.envelope, *country.stations.geometry]
    ).bounds
    bounding_box = (
        min_x - BOUNDING_BOX_PADDING_DEGREES,
        min_y - BOUNDING_BOX_PADDING_DEGREES,
        max_x + BOUNDING_BOX_PADDING_DEGREES,
        max_y + BOUNDING_BOX_PADDING_DEGREES,
    )
    basins: dict[int, gpd.GeoDataFrame] = {}
    for level in range(MIN_LEVEL, MAX_LEVEL + 1):
        filepath = basins_directory / f"hybas_{country.region}_lev{level:02d}_v1c.shp"
        basins[level] = gpd.read_file(
            filepath, bbox=bounding_box, columns=BASIN_COLUMNS
        ).to_crs(GEOGRAPHIC_CRS)
    print(
        f"{country.country_code}: loaded basins, "
        f"{len(basins[MAX_LEVEL])} polygons at level {MAX_LEVEL}"
    )
    return basins


def merge_basins(
    basins_per_country: list[dict[int, gpd.GeoDataFrame]],
) -> dict[int, gpd.GeoDataFrame]:
    merged: dict[int, gpd.GeoDataFrame] = {}
    for level in range(MIN_LEVEL, MAX_LEVEL + 1):
        combined = pd.concat(
            [basins[level] for basins in basins_per_country], ignore_index=True
        ).drop_duplicates(subset="HYBAS_ID")
        merged[level] = gpd.GeoDataFrame(combined, crs=GEOGRAPHIC_CRS).reset_index(
            drop=True
        )
    return merged


# --- The rule ---------------------------------------------------------------


def _find_highest_unique_basin(
    stations: gpd.GeoDataFrame,
    basins: dict[int, gpd.GeoDataFrame],
    max_basin_area_km2: float,
) -> dict[str, tuple[int, int]]:
    """Copied from PR #99 (`_find_highest_unique_basin`), minus the prints.

    Returns stationCode -> (HYBAS_ID, level) for the coarsest level at which the
    station is the only one of its `_country` group in a basin within the area cap.
    """
    joins = {}
    for level, basin_gdf in basins.items():
        small_enough = basin_gdf[basin_gdf["SUB_AREA"] <= max_basin_area_km2]
        joined = gpd.sjoin(
            stations,
            small_enough[["HYBAS_ID", "geometry"]],
            how="left",
            predicate="within",
        )
        joins[level] = joined[["stationCode", "_country", "HYBAS_ID"]].copy()
        joins[level]["level"] = level

    for level, df in joins.items():
        counts = (
            df.groupby(["_country", "HYBAS_ID"])
            .size()
            .reset_index(name="n_same_country")
        )
        joins[level] = df.merge(counts, on=["_country", "HYBAS_ID"], how="left")

    best: dict[str, tuple[int, int]] = {}
    for level in sorted(joins.keys()):
        df = joins[level]
        alone = df[df["n_same_country"] == 1]
        for _, row in alone.iterrows():
            code = row["stationCode"]
            if code not in best:
                best[code] = (int(row["HYBAS_ID"]), level)
    return best


def _locate_stations(
    stations: gpd.GeoDataFrame, basins: dict[int, gpd.GeoDataFrame]
) -> pd.DataFrame:
    """The basin containing each station at each level, without the area cap."""
    frames = []
    for level, basin_gdf in basins.items():
        joined = gpd.sjoin(
            stations,
            basin_gdf[["HYBAS_ID", "SUB_AREA", "UP_AREA", "geometry"]],
            how="left",
            predicate="within",
        )
        frame = pd.DataFrame(
            joined[["stationCode", "country", "HYBAS_ID", "SUB_AREA", "UP_AREA"]]
        )
        frame["level"] = level
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _cross_check_assignment(
    locations: pd.DataFrame,
    assignment: dict[str, tuple[int, int]],
    group_by_country: bool,
) -> None:
    """Re-derive the rule independently of the PR code and compare."""
    expected: dict[str, tuple[int, int]] = {}
    for station_code in locations["stationCode"].unique():
        for level in range(MIN_LEVEL, MAX_LEVEL + 1):
            own, others = _split_basin_occupants(
                locations, station_code, level, group_by_country
            )
            if own is None or own["SUB_AREA"] > MAX_BASIN_AREA_KM2 or others:
                continue
            expected[station_code] = (int(own["HYBAS_ID"]), level)
            break
    if expected != assignment:
        raise AssertionError("PR rule and independent re-derivation disagree")


def _split_basin_occupants(
    locations: pd.DataFrame, station_code: str, level: int, group_by_country: bool
) -> tuple[pd.Series | None, list[str]]:
    """The station's own basin row at a level and the other stations in that basin."""
    at_level = locations[locations["level"] == level]
    own_rows = at_level[at_level["stationCode"] == station_code]
    if own_rows.empty or pd.isna(own_rows.iloc[0]["HYBAS_ID"]):
        return None, []
    own = own_rows.iloc[0]
    same_basin = at_level[
        (at_level["HYBAS_ID"] == own["HYBAS_ID"])
        & (at_level["stationCode"] != station_code)
    ]
    if group_by_country:
        same_basin = same_basin[same_basin["country"] == own["country"]]
    return own, sorted(same_basin["stationCode"])


# --- Per-station description --------------------------------------------------


def _describe_stations(
    countries: dict[str, CountryInputs],
    basins: dict[int, gpd.GeoDataFrame],
    assignment: dict[str, tuple[int, int]],
    locations: pd.DataFrame,
    group_by_country: bool,
) -> list[dict]:
    rows: list[dict] = []
    for country in countries.values():
        outline_equal_area = _to_equal_area(country.outline_without_holes)
        for station in country.stations.itertuples():
            station_code: str = station.stationCode
            footprint = country.footprints[station_code]
            row: dict = {
                "country": country.country_code,
                "station_code": station_code,
                "station_name": station.station_name,
                "latitude": station.geometry.y,
                "longitude": station.geometry.x,
                "station_inside_country": country.outline_without_holes.covers(
                    station.geometry
                ),
                "station_geometry": station.geometry,
                "footprint_geometry": footprint,
                "basin_geometry": None,
                "basin_level": pd.NA,
                "hybas_id": pd.NA,
                "basin_area_km2": np.nan,
                "basin_outlet_upstream_area_km2": np.nan,
                "upstream_area_at_station_km2": _upstream_area_at_station(
                    locations, station_code
                ),
                "next_down_hybas_id": pd.NA,
                "lumped_coastal_basin": pd.NA,
                "endorheic": pd.NA,
                "basin_polygon_parts": pd.NA,
                "no_basin_found": station_code not in assignment,
                "basin_under_100_km2": False,
                "basin_extends_outside_country": False,
                "basin_share_outside_country": np.nan,
                "basin_area_inside_country_km2": np.nan,
                "polygon_area_to_sub_area_ratio": np.nan,
                "current_admin_area_count": country.admin_area_counts[station_code],
                **country.footprint_part_summaries[station_code],
                "current_footprint_area_km2": np.nan,
                "station_inside_current_footprint": pd.NA,
                "share_of_current_footprint_in_basin": np.nan,
                "share_of_basin_in_current_footprint": np.nan,
                "flooded_10_year_in_current_footprint_km2": np.nan,
                "flooded_10_year_in_basin_km2": np.nan,
                "flooded_10_year_in_both_km2": np.nan,
            }
            footprint_equal_area = None
            if footprint is not None:
                footprint_equal_area = _to_equal_area(footprint)
                row["current_footprint_area_km2"] = _area_km2(footprint_equal_area)
                row["station_inside_current_footprint"] = footprint.covers(
                    station.geometry
                )

            if station_code in assignment:
                hybas_id, level = assignment[station_code]
                basin = basins[level][basins[level]["HYBAS_ID"] == hybas_id].iloc[0]
                basin_equal_area = _to_equal_area(basin.geometry)
                polygon_area = _area_km2(basin_equal_area)
                inside_area = _area_km2(
                    basin_equal_area.intersection(outline_equal_area)
                )
                share_outside = max(0.0, 1 - inside_area / polygon_area)
                row.update(
                    {
                        "basin_geometry": basin.geometry,
                        "basin_level": level,
                        "hybas_id": hybas_id,
                        "basin_area_km2": float(basin["SUB_AREA"]),
                        "basin_outlet_upstream_area_km2": float(basin["UP_AREA"]),
                        "next_down_hybas_id": int(basin["NEXT_DOWN"]),
                        "lumped_coastal_basin": bool(basin["COAST"]),
                        "endorheic": int(basin["ENDO"]) != 0,
                        "basin_polygon_parts": _count_parts(basin.geometry),
                        "basin_under_100_km2": float(basin["SUB_AREA"])
                        < MIN_BASIN_AREA_KM2,
                        "basin_extends_outside_country": share_outside
                        > OUTSIDE_COUNTRY_SHARE_THRESHOLD,
                        "basin_share_outside_country": share_outside,
                        "basin_area_inside_country_km2": inside_area,
                        "polygon_area_to_sub_area_ratio": polygon_area
                        / float(basin["SUB_AREA"]),
                    }
                )
                if footprint_equal_area is not None:
                    overlap = _area_km2(
                        basin_equal_area.intersection(footprint_equal_area)
                    )
                    row["share_of_current_footprint_in_basin"] = (
                        overlap / row["current_footprint_area_km2"]
                    )
                    row["share_of_basin_in_current_footprint"] = overlap / polygon_area

            row["limited_by"] = _explain_limit(
                locations, station_code, assignment.get(station_code), group_by_country
            )
            rows.append(row)
    return rows


def _upstream_area_at_station(locations: pd.DataFrame, station_code: str) -> float:
    """`UP_AREA` of the finest polygon holding the station: a rough proxy only."""
    finest = locations[
        (locations["stationCode"] == station_code) & (locations["level"] == MAX_LEVEL)
    ]
    return float(finest.iloc[0]["UP_AREA"])


def _explain_limit(
    locations: pd.DataFrame,
    station_code: str,
    assigned: tuple[int, int] | None,
    group_by_country: bool,
) -> str:
    """Why the station did not get a coarser basin (or any basin at all)."""
    if assigned is not None and assigned[1] == MIN_LEVEL:
        return f"coarsest level allowed (level {MIN_LEVEL})"
    blocking_level = MAX_LEVEL if assigned is None else assigned[1] - 1
    own, others = _split_basin_occupants(
        locations, station_code, blocking_level, group_by_country
    )
    if own is None:
        return f"station is not inside any level-{blocking_level} polygon"
    if own["SUB_AREA"] > MAX_BASIN_AREA_KM2:
        return f"area cap: level-{blocking_level} basin is {own['SUB_AREA']:,.0f} km²"
    return (
        f"other station: level-{blocking_level} basin ({own['SUB_AREA']:,.0f} km²) "
        f"also holds {', '.join(others)}"
    )


def _to_equal_area(geometry: BaseGeometry) -> BaseGeometry:
    projected = gpd.GeoSeries([geometry], crs=GEOGRAPHIC_CRS).to_crs(EQUAL_AREA_CRS)
    return shapely.make_valid(projected.iloc[0])


def _area_km2(equal_area_geometry: BaseGeometry) -> float:
    return equal_area_geometry.area / SQUARE_METRES_PER_KM2


def _count_parts(geometry: BaseGeometry | None) -> int:
    if geometry is None:
        return 0
    return len(shapely.get_parts(geometry))


# --- Summaries ----------------------------------------------------------------

GEOMETRY_COLUMNS = ["station_geometry", "footprint_geometry", "basin_geometry"]
CHANGED_STATION_COLUMNS = [
    "country",
    "station_code",
    "station_name",
    "basin_level",
    "hybas_id",
    "basin_area_km2",
    "limited_by",
    "all_countries_run_basin_level",
    "all_countries_run_hybas_id",
    "all_countries_run_basin_area_km2",
    "all_countries_run_limited_by",
]


SEPARATE_PARTS_COLUMNS = [
    "country",
    "station_code",
    "station_name",
    "current_admin_area_count",
    "current_footprint_part_count",
    "current_footprint_admin_areas_per_part",
    "smallest_gap_between_footprint_parts_km",
    "largest_gap_between_footprint_parts_km",
]


def _build_station_summary(
    same_country_rows: list[dict], all_countries_rows: list[dict]
) -> pd.DataFrame:
    summary = pd.DataFrame(same_country_rows).drop(columns=GEOMETRY_COLUMNS)
    other = pd.DataFrame(all_countries_rows).set_index("station_code")
    for column in ["basin_level", "hybas_id", "basin_area_km2", "limited_by"]:
        summary[f"all_countries_run_{column}"] = (
            other[column].reindex(summary["station_code"]).to_numpy()
        )
    summary["all_countries_run_no_basin_found"] = (
        other["no_basin_found"].reindex(summary["station_code"]).to_numpy()
    )
    summary["basin_changes_in_all_countries_run"] = [
        _differs(first, second)
        for first, second in zip(
            summary["hybas_id"], summary["all_countries_run_hybas_id"], strict=True
        )
    ]
    for column in ["basin_level", "hybas_id", "next_down_hybas_id"]:
        summary[column] = summary[column].astype("Int64")
    for column in ["all_countries_run_basin_level", "all_countries_run_hybas_id"]:
        summary[column] = summary[column].astype("Int64")
    return summary


def _differs(first: object, second: object) -> bool:
    if pd.isna(first) and pd.isna(second):
        return False
    if pd.isna(first) or pd.isna(second):
        return True
    return first != second


def _build_country_summary(
    countries: dict[str, CountryInputs],
    same_country_rows: list[dict],
    all_countries_rows: list[dict],
) -> pd.DataFrame:
    summaries: list[dict] = []
    for country in countries.values():
        rows = [
            row for row in same_country_rows if row["country"] == country.country_code
        ]
        pooled_rows = [
            row for row in all_countries_rows if row["country"] == country.country_code
        ]
        outline = _to_equal_area(country.outline)
        country_area = _area_km2(outline)
        summaries.append(
            {
                "country": country.country_code,
                "country_name": country.country_name,
                "flood_admin_level": country.admin_level,
                "country_area_km2": country_area,
                "stations": len(rows),
                "basins_found": sum(not row["no_basin_found"] for row in rows),
                "stations_without_basin": _codes(rows, "no_basin_found"),
                "stations_with_basin_under_100_km2": _codes(
                    rows, "basin_under_100_km2"
                ),
                "stations_with_basin_extending_outside_country": _codes(
                    rows, "basin_extends_outside_country"
                ),
                "share_covered_today": _covered_share(
                    [row["footprint_geometry"] for row in rows], outline, country_area
                ),
                "share_covered_under_rule": _covered_share(
                    [row["basin_geometry"] for row in rows], outline, country_area
                ),
                "share_of_todays_coverage_kept_under_rule": _kept_share(rows, outline),
                "share_covered_under_rule_dropping_under_100_km2": _covered_share(
                    _basins_at_least_minimum(rows), outline, country_area
                ),
                "all_countries_run_basins_found": sum(
                    not row["no_basin_found"] for row in pooled_rows
                ),
                "all_countries_run_share_covered_under_rule": _covered_share(
                    [row["basin_geometry"] for row in pooled_rows],
                    outline,
                    country_area,
                ),
                "all_countries_run_share_covered_dropping_under_100_km2": (
                    _covered_share(
                        _basins_at_least_minimum(pooled_rows), outline, country_area
                    )
                ),
            }
        )
    return pd.DataFrame(summaries)


def _codes(rows: list[dict], flag: str) -> str:
    return " ".join(row["station_code"] for row in rows if row[flag])


def _basins_at_least_minimum(rows: list[dict]) -> list[BaseGeometry | None]:
    return [row["basin_geometry"] for row in rows if not row["basin_under_100_km2"]]


def _covered_share(
    geometries: list[BaseGeometry | None],
    outline_equal_area: BaseGeometry,
    country_area_km2: float,
) -> float:
    """Share of the country inside the union of the geometries (clipped to it)."""
    present = [geometry for geometry in geometries if geometry is not None]
    if not present:
        return 0.0
    union = _to_equal_area(shapely.union_all(present))
    return _area_km2(union.intersection(outline_equal_area)) / country_area_km2


def _kept_share(rows: list[dict], outline_equal_area: BaseGeometry) -> float:
    """Share of the area covered today that is still covered under the rule."""
    footprints = [
        row["footprint_geometry"]
        for row in rows
        if row["footprint_geometry"] is not None
    ]
    basins = [
        row["basin_geometry"] for row in rows if row["basin_geometry"] is not None
    ]
    if not footprints or not basins:
        return 0.0
    covered_today = _to_equal_area(shapely.union_all(footprints)).intersection(
        outline_equal_area
    )
    covered_under_rule = _to_equal_area(shapely.union_all(basins))
    return covered_today.intersection(covered_under_rule).area / covered_today.area


def _write_station_basins(rows: list[dict], filename: str) -> None:
    with_basin = [row for row in rows if row["basin_geometry"] is not None]
    basins = gpd.GeoDataFrame(
        {
            "country": [row["country"] for row in with_basin],
            "station_code": [row["station_code"] for row in with_basin],
            "station_name": [row["station_name"] for row in with_basin],
            "basin_level": [row["basin_level"] for row in with_basin],
            "hybas_id": [row["hybas_id"] for row in with_basin],
            "basin_area_km2": [row["basin_area_km2"] for row in with_basin],
        },
        geometry=[row["basin_geometry"] for row in with_basin],
        crs=GEOGRAPHIC_CRS,
    )
    CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    basins.to_file(CACHE_DIRECTORY / filename, driver="GeoJSON")


# --- Maps ---------------------------------------------------------------------

UNCOVERED_LAND_COLOUR = "#e4e4e4"
OTHER_COUNTRY_COLOUR = "#f6f6f6"
NO_BASIN_COLOUR = "#d00000"
SMALL_BASIN_COLOUR = "#000000"
BASIN_FILL_ALPHA = 0.6
FOOTPRINT_DARKENING = 0.55
EXTENT_PADDING_SHARE = 0.03
FIGURE_SIZE_INCHES = (16, 9)
FIGURE_DPI = 150


def _plot_all_maps(
    countries: dict[str, CountryInputs],
    same_country_rows: list[dict],
    all_countries_rows: list[dict],
    country_summary: pd.DataFrame,
) -> dict[str, list[Path]]:
    maps_directory = OUTPUT_DIRECTORY / "maps"
    pooled_maps_directory = maps_directory / "all-countries-run"
    pooled_maps_directory.mkdir(parents=True, exist_ok=True)
    plot_outlines = {
        country_code: country.outline.simplify(PLOT_SIMPLIFY_TOLERANCE_DEGREES)
        for country_code, country in countries.items()
    }
    summary_by_country = country_summary.set_index("country")
    map_paths: dict[str, list[Path]] = {SAME_COUNTRY_SCOPE: [], ALL_COUNTRIES_SCOPE: []}

    for country_code, country in countries.items():
        rows = [row for row in same_country_rows if row["country"] == country_code]
        pooled_rows = [
            row for row in all_countries_rows if row["country"] == country_code
        ]
        summary = summary_by_country.loc[country_code]
        path = maps_directory / f"{country_code}_station_basins.png"
        _plot_country_map(
            country,
            rows,
            plot_outlines,
            path,
            scope_description="other stations counted per country (as in PR #99)",
            share_today=summary["share_covered_today"],
            share_rule=summary["share_covered_under_rule"],
            share_rule_minimum=summary[
                "share_covered_under_rule_dropping_under_100_km2"
            ],
        )
        map_paths[SAME_COUNTRY_SCOPE].append(path)

        changed = any(
            _differs(row["hybas_id"], pooled_row["hybas_id"])
            for row, pooled_row in zip(rows, pooled_rows, strict=True)
        )
        if changed:
            pooled_path = (
                pooled_maps_directory
                / f"{country_code}_station_basins_all_countries_run.png"
            )
            _plot_country_map(
                country,
                pooled_rows,
                plot_outlines,
                pooled_path,
                scope_description="other stations counted across all seven countries",
                share_today=summary["share_covered_today"],
                share_rule=summary["all_countries_run_share_covered_under_rule"],
                share_rule_minimum=summary[
                    "all_countries_run_share_covered_dropping_under_100_km2"
                ],
            )
            map_paths[ALL_COUNTRIES_SCOPE].append(pooled_path)
    return map_paths


def _plot_country_map(
    country: CountryInputs,
    rows: list[dict],
    plot_outlines: dict[str, BaseGeometry],
    path: Path,
    scope_description: str,
    share_today: float,
    share_rule: float,
    share_rule_minimum: float,
) -> None:
    colours = station_colours(len(rows))
    figure = plt.figure(figsize=FIGURE_SIZE_INCHES, dpi=FIGURE_DPI)
    axes = figure.add_axes((0.02, 0.07, 0.62, 0.83))
    outline = plot_outlines[country.country_code]

    for other_code, other_outline in plot_outlines.items():
        if other_code != country.country_code:
            plot_geometry(
                axes,
                other_outline,
                facecolor=OTHER_COUNTRY_COLOUR,
                edgecolor="#b0b0b0",
                linewidth=0.5,
                zorder=1,
            )
    plot_geometry(
        axes, outline, facecolor=UNCOVERED_LAND_COLOUR, edgecolor="none", zorder=2
    )
    for row, colour in zip(rows, colours, strict=True):
        if row["basin_geometry"] is not None:
            plot_geometry(
                axes,
                row["basin_geometry"].simplify(PLOT_SIMPLIFY_TOLERANCE_DEGREES),
                facecolor=(*colour, BASIN_FILL_ALPHA),
                edgecolor=darken(colour, 0.8),
                linewidth=0.7,
                zorder=3,
            )
    plot_geometry(
        axes, outline, facecolor="none", edgecolor="black", linewidth=1.0, zorder=4
    )
    for row, colour in zip(rows, colours, strict=True):
        if row["footprint_geometry"] is not None:
            plot_geometry(
                axes,
                row["footprint_geometry"].simplify(PLOT_SIMPLIFY_TOLERANCE_DEGREES),
                facecolor="none",
                edgecolor=darken(colour, FOOTPRINT_DARKENING),
                linewidth=1.3,
                linestyle=(0, (4, 2)),
                zorder=5,
            )
    for row, colour in zip(rows, colours, strict=True):
        _plot_station(axes, row, colour)

    _set_extent(axes, country, rows)
    axes.tick_params(labelsize=8)
    _label_stations(axes, rows)
    axes.set_xlabel("")
    axes.set_ylabel("")

    basins_found = sum(not row["no_basin_found"] for row in rows)
    figure.suptitle(
        f"{country.country_name}: one HydroBASINS basin per GloFAS station "
        f"({basins_found} of {len(rows)} stations get a basin)",
        x=0.02,
        y=0.975,
        ha="left",
        fontsize=17,
        fontweight="bold",
    )
    figure.text(
        0.02,
        0.925,
        f"Rule: largest basin (levels {MIN_LEVEL}–{MAX_LEVEL}, at most "
        f"{MAX_BASIN_AREA_KM2:,} km²) containing the station and no other station; "
        f"{scope_description}.",
        fontsize=10.5,
    )
    figure.text(
        0.02,
        0.02,
        f"Share of {country.country_name} covered: today {share_today:.0%} "
        f"(admin level {country.admin_level} footprints)  →  rule {share_rule:.0%}"
        f"  →  rule without basins under {MIN_BASIN_AREA_KM2} km² "
        f"{share_rule_minimum:.0%}.   "
        "Basins: HydroBASINS v1.c, areas from SUB_AREA.",
        fontsize=10.5,
    )
    _add_legends(figure, rows, colours)
    figure.savefig(path)
    plt.close(figure)
    print(f"Wrote {path}")


def station_colours(count: int) -> list[tuple[float, float, float]]:
    tab20 = plt.get_cmap("tab20").colors
    tab20b = plt.get_cmap("tab20b").colors
    # Saturated tab20 colours first, then their pale variants, then tab20b.
    # Grey (tab20 indices 14 and 15) is reserved for uncovered land.
    palette = [
        *[tab20[index] for index in range(0, 20, 2) if index != 14],
        *[tab20b[index] for index in (0, 4, 8, 12, 16)],
        *[tab20[index] for index in range(1, 20, 2) if index != 15],
        *[tab20b[index] for index in (2, 6, 10, 14, 18)],
    ]
    return [to_rgb(palette[index % len(palette)]) for index in range(count)]


def darken(colour: tuple[float, float, float], factor: float) -> tuple[float, ...]:
    return tuple(channel * factor for channel in colour)


def plot_geometry(axes: Axes, geometry: BaseGeometry, **style: object) -> None:
    if geometry.is_empty:
        return
    gpd.GeoSeries([geometry]).plot(ax=axes, aspect=None, **style)


def _plot_station(axes: Axes, row: dict, colour: tuple[float, float, float]) -> None:
    point: Point = row["station_geometry"]
    if row["no_basin_found"]:
        axes.scatter(
            point.x,
            point.y,
            marker="X",
            s=170,
            color=NO_BASIN_COLOUR,
            edgecolor="black",
            linewidth=0.8,
            zorder=8,
        )
    else:
        if row["basin_under_100_km2"]:
            axes.scatter(
                point.x,
                point.y,
                marker="o",
                s=330,
                facecolor="none",
                edgecolor=SMALL_BASIN_COLOUR,
                linewidth=1.6,
                zorder=7,
            )
        axes.scatter(
            point.x,
            point.y,
            marker="o",
            s=55,
            color=colour,
            edgecolor="black",
            linewidth=0.9,
            zorder=8,
        )


def _label_stations(axes: Axes, rows: list[dict]) -> None:
    labels = []
    for row in rows:
        point: Point = row["station_geometry"]
        label = axes.text(
            point.x,
            point.y,
            row["station_code"],
            fontsize=8.5,
            fontweight="bold",
            color=NO_BASIN_COLOUR if row["no_basin_found"] else "black",
            zorder=9,
        )
        label.set_path_effects(
            [path_effects.withStroke(linewidth=2.5, foreground="white")]
        )
        labels.append(label)
    adjust_text(
        labels,
        x=[row["station_geometry"].x for row in rows],
        y=[row["station_geometry"].y for row in rows],
        ax=axes,
        expand=(1.3, 1.5),
        arrowprops={"arrowstyle": "-", "color": "black", "linewidth": 0.6},
    )


def _set_extent(axes: Axes, country: CountryInputs, rows: list[dict]) -> None:
    geometries = [country.outline.envelope]
    for row in rows:
        geometries.append(row["station_geometry"])
        for key in ("basin_geometry", "footprint_geometry"):
            if row[key] is not None:
                geometries.append(row[key].envelope)
    fit_extent(axes, shapely.union_all(geometries).bounds)


def fit_extent(
    axes: Axes,
    bounds: tuple[float, float, float, float],
    padding_share: float = EXTENT_PADDING_SHARE,
) -> None:
    """Show the bounds with padding, widened to fill the axes at true proportions."""
    min_x, min_y, max_x, max_y = bounds
    padding = padding_share * max(max_x - min_x, max_y - min_y)
    width = max_x - min_x + 2 * padding
    height = max_y - min_y + 2 * padding
    degrees_x_per_degree_y = 1 / np.cos(np.radians((min_y + max_y) / 2))
    box = axes.get_window_extent()
    width_to_fill_box = height * box.width / box.height * degrees_x_per_degree_y
    if width_to_fill_box > width:
        width = width_to_fill_box
    else:
        height = width / degrees_x_per_degree_y * box.height / box.width
    centre_x, centre_y = (min_x + max_x) / 2, (min_y + max_y) / 2
    axes.set_xlim(centre_x - width / 2, centre_x + width / 2)
    axes.set_ylim(centre_y - height / 2, centre_y + height / 2)
    axes.set_aspect(degrees_x_per_degree_y)


def _add_legends(
    figure: plt.Figure, rows: list[dict], colours: list[tuple[float, float, float]]
) -> None:
    key_handles = [
        Patch(
            facecolor="#7fa8d0",
            alpha=BASIN_FILL_ALPHA,
            edgecolor="#40607c",
            label="Station basin under the rule (one colour per station)",
        ),
        Line2D(
            [],
            [],
            color="#404040",
            linewidth=1.3,
            linestyle=(0, (4, 2)),
            label="Current admin-area footprint (darker shade of station colour)",
        ),
        Patch(
            facecolor=UNCOVERED_LAND_COLOUR,
            edgecolor="black",
            label="Land in no station basin",
        ),
        Line2D(
            [],
            [],
            marker="o",
            linestyle="none",
            markersize=7,
            markerfacecolor="#7fa8d0",
            markeredgecolor="black",
            label="Station with basin",
        ),
        Line2D(
            [],
            [],
            marker="X",
            linestyle="none",
            markersize=11,
            markerfacecolor=NO_BASIN_COLOUR,
            markeredgecolor="black",
            label="Station with no basin",
        ),
        Line2D(
            [],
            [],
            marker="o",
            linestyle="none",
            markersize=13,
            markerfacecolor="none",
            markeredgecolor=SMALL_BASIN_COLOUR,
            markeredgewidth=1.6,
            label=f"Basin under {MIN_BASIN_AREA_KM2} km² (proposed: drop station)",
        ),
    ]
    figure.legend(
        handles=key_handles,
        loc="upper left",
        bbox_to_anchor=(0.655, 0.905),
        fontsize=9.5,
        frameon=False,
        title="Key",
        title_fontsize=11,
        alignment="left",
    )
    station_handles = [
        Patch(
            facecolor="white" if row["no_basin_found"] else (*colour, BASIN_FILL_ALPHA),
            edgecolor=NO_BASIN_COLOUR if row["no_basin_found"] else darken(colour, 0.8),
            label=_station_legend_label(row),
        )
        for row, colour in zip(rows, colours, strict=True)
    ]
    figure.legend(
        handles=station_handles,
        loc="upper left",
        bbox_to_anchor=(0.655, 0.66),
        fontsize=8.6 if len(rows) <= 20 else 7.6,
        frameon=False,
        title="Stations: basin level, basin area, share outside country",
        title_fontsize=11,
        alignment="left",
    )


def _station_legend_label(row: dict) -> str:
    prefix = f"{row['station_code']}  {_format_name(row['station_name'])[:30]}".rstrip()
    if row["no_basin_found"]:
        return f"{prefix}: no basin"
    label = f"{prefix}: level {row['basin_level']}, {row['basin_area_km2']:,.0f} km²"
    if row["basin_extends_outside_country"]:
        label += f", {row['basin_share_outside_country']:.0%} outside"
    return label


# --- Flood map and before-and-after figures ------------------------------------

FLOOD_INSIDE_COLOUR = "#0b5cad"
FLOOD_OUTSIDE_COLOUR = "#b9c7d6"
AREA_FILL_COLOUR = "#fff1c9"
AREA_EDGE_COLOUR = "#8a6d1c"
MAX_PLOT_PIXELS = 2500


def _analyse_flood_maps(
    countries: dict[str, CountryInputs],
    same_country_rows: list[dict],
    all_countries_rows: list[dict],
    seed_repository_root: Path,
    before_after_stations: list[str],
) -> list[Path]:
    """Add the flooded area inside footprint and basin to every row, and plot
    the before-and-after figure of the requested stations."""
    figures_directory = OUTPUT_DIRECTORY / "before-after"
    figures_directory.mkdir(exist_ok=True)
    paths: list[Path] = []
    for country in countries.values():
        flood_map = load_flood_map(seed_repository_root, country.country_code)
        for rows in (same_country_rows, all_countries_rows):
            for row in rows:
                if row["country"] == country.country_code:
                    _add_flooded_areas(row, flood_map, country.outline_without_holes)
        for row in same_country_rows:
            if (
                row["country"] == country.country_code
                and row["station_code"] in before_after_stations
            ):
                path = figures_directory / (
                    f"{country.country_code}_{row['station_code']}_before_after.png"
                )
                _plot_before_after(country, row, flood_map, path)
                paths.append(path)
        print(f"{country.country_code}: flood map analysed")
    return paths


def load_flood_map(seed_repository_root: Path, country_code: str) -> FloodMap:
    name = f"{country_code}_flood_extent_rp{FLOOD_RETURN_PERIOD_YEARS}"
    directory = seed_repository_root / FLOOD_MAPS_DIRECTORY
    metadata = load_json(directory / f"{name}_metadata.json")
    if not isinstance(metadata, dict):
        raise TypeError(f"Unexpected flood map metadata for {country_code}")
    transform = Affine(*metadata["transform"][:6])

    FLOOD_MASK_CACHE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    cache_path = FLOOD_MASK_CACHE_DIRECTORY / f"{name}.npz"
    if cache_path.exists():
        return FloodMap(np.load(cache_path)["flooded"], transform)

    Image.MAX_IMAGE_PIXELS = None  # noqa: V101
    with Image.open(directory / f"{name}.png") as image:
        # The depth is spread over the four channels; any non-zero channel is water.
        flooded = np.asarray(image.convert("RGBA")).any(axis=2)
    np.savez_compressed(cache_path, flooded=flooded)
    return FloodMap(flooded, transform)


def _add_flooded_areas(
    row: dict, flood_map: FloodMap, country_outline: BaseGeometry
) -> None:
    """Flooded area inside the country only: the flood maps stop at a bounding
    box around the country, so basins are not fully covered beyond the border."""
    footprint = row["footprint_geometry"]
    basin = row["basin_geometry"]
    if basin is not None:
        basin = basin.intersection(country_outline)
    if footprint is not None:
        row["flooded_10_year_in_current_footprint_km2"] = _flooded_area_km2(
            flood_map, footprint
        )
    if basin is not None:
        row["flooded_10_year_in_basin_km2"] = _flooded_area_km2(flood_map, basin)
    if footprint is not None and basin is not None:
        row["flooded_10_year_in_both_km2"] = _flooded_area_km2(
            flood_map, footprint.intersection(basin)
        )


def _flooded_area_km2(flood_map: FloodMap, geometry: BaseGeometry) -> float:
    if geometry.is_empty:
        return 0.0
    flooded, transform = _flood_window(flood_map, geometry.bounds)
    if flooded.size == 0:
        return 0.0
    inside = _pixels_inside(geometry, flooded.shape, transform)
    flooded_pixels_per_row = (flooded & inside).sum(axis=1)
    return float(
        (flooded_pixels_per_row * pixel_areas_km2(transform, len(flooded))).sum()
    )


def _flood_window(
    flood_map: FloodMap, bounds: tuple[float, float, float, float]
) -> tuple[np.ndarray, Affine]:
    """The part of the flood map inside the bounds, and its transform."""
    min_x, min_y, max_x, max_y = bounds
    transform = flood_map.transform
    height, width = flood_map.flooded.shape
    column_start = max(0, int(np.floor((min_x - transform.c) / transform.a)))
    column_stop = min(width, int(np.ceil((max_x - transform.c) / transform.a)))
    row_start = max(0, int(np.floor((max_y - transform.f) / transform.e)))
    row_stop = min(height, int(np.ceil((min_y - transform.f) / transform.e)))
    if column_stop <= column_start or row_stop <= row_start:
        return np.zeros((0, 0), dtype=bool), transform
    window_transform = transform * Affine.translation(column_start, row_start)
    return (
        flood_map.flooded[row_start:row_stop, column_start:column_stop],
        window_transform,
    )


def _pixels_inside(
    geometry: BaseGeometry, shape: tuple[int, int], transform: Affine
) -> np.ndarray:
    return rasterio.features.geometry_mask(
        [geometry], out_shape=shape, transform=transform, invert=True
    )


def pixel_areas_km2(transform: Affine, row_count: int) -> np.ndarray:
    """Area of one pixel in each row, on a sphere with the same area as the Earth."""
    top = np.radians(transform.f + transform.e * np.arange(row_count))
    bottom = top + np.radians(transform.e)
    return (
        AUTHALIC_EARTH_RADIUS_KM**2
        * np.radians(transform.a)
        * (np.sin(top) - np.sin(bottom))
    )


def _plot_before_after(
    country: CountryInputs, row: dict, flood_map: FloodMap, path: Path
) -> None:
    footprint: BaseGeometry = row["footprint_geometry"]
    basin: BaseGeometry = row["basin_geometry"]
    bounds = _padded_bounds(
        shapely.union_all([footprint.envelope, basin.envelope]).bounds
    )
    part_count = row["current_footprint_part_count"]
    panels = [
        (
            footprint,
            country.footprint_parts[row["station_code"]],
            (
                f"Today: {row['current_admin_area_count']} admin areas (level "
                f"{country.admin_level}) in {part_count} "
                f"{'part' if part_count == 1 else 'separate parts'}"
            ),
            row["flooded_10_year_in_current_footprint_km2"],
            row["current_footprint_area_km2"],
        ),
        (
            basin,
            [basin],
            f"Rule: one HydroBASINS basin (level {row['basin_level']})",
            row["flooded_10_year_in_basin_km2"],
            row["basin_area_inside_country_km2"],
        ),
    ]

    figure = plt.figure(figsize=FIGURE_SIZE_INCHES, dpi=FIGURE_DPI)
    name = _format_name(row["station_name"])
    figure.suptitle(
        f"{country.country_name}, station {row['station_code']} {name}".rstrip()
        + ": today's admin areas and the basin from the rule",
        x=0.02,
        y=0.975,
        ha="left",
        fontsize=17,
        fontweight="bold",
    )
    figure.text(
        0.02,
        0.925,
        f"The {FLOOD_RETURN_PERIOD_YEARS}-year flood map clipped to the area mapped "
        f"to the station. Flood map shown inside {country.country_name} only.",
        fontsize=10.5,
    )
    for index, (area, outlines, title, flooded_km2, area_km2) in enumerate(panels):
        axes = figure.add_axes((0.035 + index * 0.49, 0.1, 0.455, 0.73))
        plot_geometry(
            axes,
            country.outline.simplify(PLOT_SIMPLIFY_TOLERANCE_DEGREES),
            facecolor="#f4f4f4",
            edgecolor="black",
            linewidth=0.8,
            zorder=1,
        )
        plot_geometry(
            axes, area, facecolor=AREA_FILL_COLOUR, edgecolor="none", zorder=2
        )
        fit_extent(axes, bounds, padding_share=0)
        view_bounds = (*axes.get_xlim(), *axes.get_ylim())
        flooded, transform = _flood_window(
            flood_map, (view_bounds[0], view_bounds[2], view_bounds[1], view_bounds[3])
        )
        flooded = flooded & _pixels_inside(
            country.outline_without_holes, flooded.shape, transform
        )
        inside = _pixels_inside(area, flooded.shape, transform)
        show_mask(axes, flooded & ~inside, transform, FLOOD_OUTSIDE_COLOUR, zorder=3)
        show_mask(axes, flooded & inside, transform, FLOOD_INSIDE_COLOUR, zorder=4)
        for outline in outlines:
            plot_geometry(
                axes,
                outline,
                facecolor="none",
                edgecolor=AREA_EDGE_COLOUR,
                linewidth=1.4,
                zorder=5,
            )
        station: Point = row["station_geometry"]
        axes.scatter(
            station.x,
            station.y,
            marker="o",
            s=90,
            color="#d00000",
            edgecolor="black",
            linewidth=1.0,
            zorder=6,
        )
        axes.set_xlim(view_bounds[0], view_bounds[1])
        axes.set_ylim(view_bounds[2], view_bounds[3])
        axes.tick_params(labelsize=8)
        axes.set_xlabel("")
        axes.set_ylabel("")
        axes.set_title(
            f"{title}\n{area_km2:,.0f} km² in {country.country_name}, of which "
            f"{flooded_km2:,.0f} km² in the {FLOOD_RETURN_PERIOD_YEARS}-year flood map",
            fontsize=12.5,
            loc="left",
        )
    figure.legend(
        handles=[
            Patch(
                facecolor=AREA_FILL_COLOUR,
                edgecolor=AREA_EDGE_COLOUR,
                label="Area mapped to the station",
            ),
            Patch(
                facecolor=FLOOD_INSIDE_COLOUR,
                label=f"{FLOOD_RETURN_PERIOD_YEARS}-year flood map inside that area",
            ),
            Patch(
                facecolor=FLOOD_OUTSIDE_COLOUR,
                label=f"{FLOOD_RETURN_PERIOD_YEARS}-year flood map outside it",
            ),
            Line2D(
                [],
                [],
                marker="o",
                linestyle="none",
                markersize=9,
                markerfacecolor="#d00000",
                markeredgecolor="black",
                label="GloFAS station",
            ),
        ],
        loc="lower left",
        bbox_to_anchor=(0.03, 0.005),
        ncols=4,
        fontsize=11,
        frameon=False,
    )
    figure.savefig(path)
    plt.close(figure)
    print(f"Wrote {path}")


def _padded_bounds(
    bounds: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    min_x, min_y, max_x, max_y = bounds
    padding = 0.08 * max(max_x - min_x, max_y - min_y)
    return (min_x - padding, min_y - padding, max_x + padding, max_y + padding)


def show_mask(
    axes: Axes, mask: np.ndarray, transform: Affine, colour: str, zorder: int
) -> None:
    if mask.size == 0:
        return
    height, width = mask.shape
    # Keep a pixel when any pixel in its block is set, so narrow rivers survive.
    factor = max(1, int(np.ceil(max(height, width) / MAX_PLOT_PIXELS)))
    padded = np.zeros(
        (int(np.ceil(height / factor)) * factor, int(np.ceil(width / factor)) * factor),
        dtype=bool,
    )
    padded[:height, :width] = mask
    pooled = padded.reshape(
        padded.shape[0] // factor, factor, padded.shape[1] // factor, factor
    ).any(axis=(1, 3))
    image = np.zeros((*pooled.shape, 4))
    image[pooled] = (*to_rgb(colour), 1.0)
    axes.imshow(
        image,
        extent=(
            transform.c,
            transform.c + padded.shape[1] * transform.a,
            transform.f + padded.shape[0] * transform.e,
            transform.f,
        ),
        interpolation="nearest",
        zorder=zorder,
    )


# --- Markdown -----------------------------------------------------------------


def _write_markdown_summary(
    station_summary: pd.DataFrame,
    country_summary: pd.DataFrame,
    changed_stations: pd.DataFrame,
    separate_parts: pd.DataFrame,
    countries: dict[str, CountryInputs],
    map_paths: dict[str, list[Path]],
    before_after_paths: list[Path],
    seed_repository_root: Path,
) -> None:
    seed_revision = _read_seed_revision(seed_repository_root)
    lines: list[str] = [
        "# Station-to-basin rule (PR #99) on current GloFAS stations",
        "",
        ("Exploratory analysis for spike AB#42674. Generated by `initial_rule.py`."),
        "",
        "## Rule",
        "",
        (
            f"Each station gets the largest HydroBASINS basin (levels {MIN_LEVEL} to "
            f"{MAX_LEVEL}) that contains it and no other station, with `SUB_AREA` of at "
            f"most {MAX_BASIN_AREA_KM2:,} km². Proposed addition, shown as a flag only: "
            f"drop a station whose basin is smaller than {MIN_BASIN_AREA_KM2} km²."
        ),
        "",
        (
            "- Run 1 (`station_summary.csv`, `maps/`): other stations are counted per "
            "country, as PR #99 does."
        ),
        (
            "- Run 2 (`all_countries_run_*` columns, `maps/all-countries-run/`): other "
            "stations are counted across all seven countries."
        ),
        "",
        "## Inputs",
        "",
        f"- Stations and admin areas: NRW-seed-data at `{seed_revision}`.",
        (
            "- Basins: HydroBASINS v1.c standard, Africa (`af`) and Australasia (`au`), "
            f"levels {MIN_LEVEL} to {MAX_LEVEL}. The Philippines is in the Australasia "
            "file, not in the Asia file."
        ),
        (
            f"- Flood map: `{FLOOD_MAPS_DIRECTORY}/{{ISO3}}_flood_extent_rp"
            f"{FLOOD_RETURN_PERIOD_YEARS}.png` from the seed repo, flooded where the "
            "depth is above zero. The GeoTIFFs in `sources-tif/` are not committed to "
            "the seed repo; the PNGs are the same grid."
        ),
        "",
        "## Per country",
        "",
        *_markdown_table(
            [
                "Country",
                "Stations",
                "Basins found",
                "No basin",
                f"Basin under {MIN_BASIN_AREA_KM2} km²",
                "Extends outside country",
                "Covered today",
                "Covered under rule",
                f"Covered, dropping under {MIN_BASIN_AREA_KM2} km²",
                "Today's coverage kept",
            ],
            [
                [
                    row["country"],
                    row["stations"],
                    row["basins_found"],
                    row["stations_without_basin"] or "-",
                    row["stations_with_basin_under_100_km2"] or "-",
                    row["stations_with_basin_extending_outside_country"] or "-",
                    f"{row['share_covered_today']:.1%}",
                    f"{row['share_covered_under_rule']:.1%}",
                    f"{row['share_covered_under_rule_dropping_under_100_km2']:.1%}",
                    f"{row['share_of_todays_coverage_kept_under_rule']:.1%}",
                ]
                for _, row in country_summary.iterrows()
            ],
        ),
        "",
        (
            "Coverage is the share of the country outline (admin level 0) inside the "
            "union of the station footprints (today) or station basins (rule), clipped "
            f"to the outline and measured in an equal-area projection ({EQUAL_AREA_CRS}). "
            '"Today\'s coverage kept" is the share of the area covered today that is '
            "also inside a station basin. "
            f'"Extends outside country" means more than '
            f"{OUTSIDE_COUNTRY_SHARE_THRESHOLD:.0%} of the basin polygon lies outside the "
            "outline with its lake holes filled; the exact share is in "
            "`station_summary.csv`. Lakes on a border (Victoria, Malawi, Turkana) still "
            "count as outside."
        ),
        "",
        "## Per station",
        "",
        *_markdown_table(
            [
                "Country",
                "Station",
                "Name",
                "Level",
                "Basin km²",
                "HYBAS_ID",
                "Outside country",
                "Today's footprint inside basin",
                "Flooded km² in footprint",
                "Flooded km² in basin",
                "Why not a larger basin",
            ],
            [
                [
                    row["country"],
                    row["station_code"],
                    _format_name(row["station_name"]),
                    _format_optional(row["basin_level"]),
                    _format_area(row["basin_area_km2"]),
                    _format_optional(row["hybas_id"]),
                    _format_share(row["basin_share_outside_country"]),
                    _format_share(row["share_of_current_footprint_in_basin"]),
                    _format_area(row["flooded_10_year_in_current_footprint_km2"]),
                    _format_area(row["flooded_10_year_in_basin_km2"]),
                    row["limited_by"],
                ]
                for _, row in station_summary.iterrows()
            ],
        ),
        "",
        (
            "\"Today's footprint inside basin\" is the share of the station's current "
            'admin-area footprint that lies inside its basin. "Flooded km²" is the '
            f"area of the {FLOOD_RETURN_PERIOD_YEARS}-year flood map inside the footprint "
            "and inside the basin, both inside the country only."
        ),
        "",
        "## Run 2: stations whose basin changes",
        "",
    ]
    if changed_stations.empty:
        lines.append("No station gets a different basin.")
    else:
        lines.extend(
            _markdown_table(
                ["Country", "Station", "Name", "Run 1", "Run 2", "Why (run 2)"],
                [
                    [
                        row["country"],
                        row["station_code"],
                        _format_name(row["station_name"]),
                        _format_basin(row["basin_level"], row["basin_area_km2"]),
                        _format_basin(
                            row["all_countries_run_basin_level"],
                            row["all_countries_run_basin_area_km2"],
                        ),
                        row["all_countries_run_limited_by"],
                    ]
                    for _, row in changed_stations.iterrows()
                ],
            )
        )
    lines.extend(
        [
            "",
            "## Stations whose current footprint is in separate parts",
            "",
            (
                "Admin areas of one station are grouped into parts; two areas are in the "
                f"same part when they are within {TOUCH_TOLERANCE_DEGREES}° (about 100 m) "
                "of each other, directly or through other areas of that station. Gaps are "
                "from each part to its nearest other part. "
                f"{len(separate_parts)} of {len(station_summary)} stations have more than "
                "one part."
            ),
            "",
            *_markdown_table(
                [
                    "Country",
                    "Station",
                    "Name",
                    "Admin areas",
                    "Parts",
                    "Admin areas per part",
                    "Smallest gap km",
                    "Largest gap km",
                ],
                [
                    [
                        row["country"],
                        row["station_code"],
                        _format_name(row["station_name"]),
                        row["current_admin_area_count"],
                        row["current_footprint_part_count"],
                        row["current_footprint_admin_areas_per_part"],
                        f"{row['smallest_gap_between_footprint_parts_km']:.1f}",
                        f"{row['largest_gap_between_footprint_parts_km']:.1f}",
                    ]
                    for _, row in separate_parts.iterrows()
                ],
            ),
        ]
    )
    lines.extend(["", "## Checks worth a hydrologist's eye", ""])
    lines.extend(_markdown_checks(station_summary, countries))
    lines.extend(["", "## Before-and-after figures", ""])
    for path in before_after_paths:
        station_code = path.name.split("_")[1]
        reason = BEFORE_AFTER_STATIONS.get(station_code, "")
        lines.append(
            f"- [{path.name}](./{path.relative_to(OUTPUT_DIRECTORY)}): {reason}".rstrip()
        )
    lines.extend(["", "## Maps", ""])
    for scope in (SAME_COUNTRY_SCOPE, ALL_COUNTRIES_SCOPE):
        for path in map_paths[scope]:
            lines.append(f"- [{path.name}](./{path.relative_to(OUTPUT_DIRECTORY)})")
    (OUTPUT_DIRECTORY / "summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _read_seed_revision(seed_repository_root: Path) -> str:
    return get_git_revision(seed_repository_root) or "unknown revision"


def _markdown_checks(
    station_summary: pd.DataFrame, countries: dict[str, CountryInputs]
) -> list[str]:
    with_basin = station_summary[~station_summary["no_basin_found"]]
    share_of_basin_upstream_area_at_station = (
        with_basin["upstream_area_at_station_km2"]
        / with_basin["basin_outlet_upstream_area_km2"]
    )
    checks = {
        "Station has no admin areas in the current mapping": station_summary[
            station_summary["current_admin_area_count"] == 0
        ],
        "Station lies outside the country outline": station_summary[
            ~station_summary["station_inside_country"]
        ],
        "Station lies outside its own current admin footprint": station_summary[
            station_summary["station_inside_current_footprint"].eq(False)
        ],
        "Basin does not overlap the current footprint at all": with_basin[
            with_basin["share_of_current_footprint_in_basin"] == 0
        ],
        "Station sits at the downstream end of its basin, so the basin is almost "
        "all upstream of it (the finest polygon at the station drains at least "
        f"{DOWNSTREAM_END_SHARE:.0%} of what the basin outlet drains)": with_basin[
            share_of_basin_upstream_area_at_station >= DOWNSTREAM_END_SHARE
        ],
        "Station is on a small tributary or headwater of a much larger basin (the "
        f"finest polygon at the station drains under {SMALL_TRIBUTARY_SHARE:.0%} of "
        "what the basin outlet drains)": with_basin[
            share_of_basin_upstream_area_at_station < SMALL_TRIBUTARY_SHARE
        ],
        "Basin is a lumped coastal unit (HydroBASINS `COAST` = 1), i.e. several "
        "small independent catchments": with_basin[
            with_basin["lumped_coastal_basin"].eq(True)
        ],
        "Basin polygon has more than one part": with_basin[
            with_basin["basin_polygon_parts"] > 1
        ],
        "Basin size is set by a neighbouring station rather than by the area "
        "cap": with_basin[with_basin["limited_by"].str.startswith("other station")],
        "Same basin assigned to stations of different countries (run 1)": with_basin[
            with_basin.duplicated("hybas_id", keep=False)
        ],
    }
    lines = [
        f"- {description}: "
        + (
            ", ".join(f"{row.country} {row.station_code}" for row in rows.itertuples())
            or "none"
        )
        for description, rows in checks.items()
    ]
    missing = {
        f"{country.country_code} {station_code}": pcodes
        for country in countries.values()
        for station_code, pcodes in country.missing_pcodes.items()
    }
    lines.append(
        "- Place codes of the current mapping missing from the admin-area file: "
        + (json.dumps(missing) if missing else "none")
    )
    return lines


def _markdown_table(header: list[str], rows: list[list[object]]) -> list[str]:
    return [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
        *["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows],
    ]


def _format_name(name: str) -> str:
    return "" if name.strip().lower() == "na" else name


def _format_optional(value: object) -> str:
    return "-" if pd.isna(value) else str(value)


def _format_area(value: float) -> str:
    return "-" if pd.isna(value) else f"{value:,.0f}"


def _format_share(value: float) -> str:
    return "-" if pd.isna(value) else f"{value:.0%}"


def _format_basin(level: object, area: float) -> str:
    if pd.isna(level):
        return "no basin"
    return f"level {level}, {area:,.0f} km²"


if __name__ == "__main__":
    main()
