"""Build the spatial extent of each GloFAS station from HydroBASINS, for the seed repo.

A station's spatial extent is the HydroBASINS polygon it lies in plus the polygons
downstream of it along the river, clipped to the country. See README.md.
"""

import argparse
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

import fiona
import shapely
from data_management.seed_data_management.admin_areas.admin_area_dataset_helpers import (
    get_feature_geometry,
    load_admin_features,
    union_geometries,
)
from data_management.seed_data_management.flood.migrate_glofas_station_area_mapping import (
    load_unique_stations,
    STATION_THRESHOLDS_DIRECTORY,
)
from shapely.geometry import mapping, MultiPolygon, Point, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shared.data_helpers import get_seed_data_repo_path

# The HydroBASINS archive that covers each country. The Philippines is in the
# Australasia archive ("au"), not in the Asia archive.
HYDROBASINS_REGIONS = {
    "ETH": "af",
    "KEN": "af",
    "MWI": "af",
    "PHL": "au",
    "SSD": "af",
    "UGA": "af",
    "ZMB": "af",
}
HYDROBASINS_LEVEL = 7
DOWNSTREAM_DISTANCE_KM = 200.0
HYDROBASINS_RIVER_END = 0  # NEXT_DOWN of a polygon at the sea or an inland sink
SHAPEFILE_SUFFIXES = (".shp", ".shx", ".dbf", ".prj")
DEFAULT_BASINS_DIRECTORY = Path(__file__).resolve().parents[3] / "data" / "hydrobasins"
COUNTRY_OUTLINE_ADMIN_LEVEL = 0
# About 100 m and 1 m: enough for an area of thousands of km², and it keeps the files small.
SIMPLIFY_TOLERANCE_DEGREES = 0.001
COORDINATE_PRECISION_DEGREES = 0.00001


@dataclass(frozen=True)
class Basin:
    next_down_id: int
    distance_to_river_end_km: float
    geometry: BaseGeometry


@dataclass(frozen=True)
class StationSpatialExtent:
    station_code: str
    hydrobasins_ids: list[int]
    geometry: BaseGeometry


def main() -> None:
    arguments = parse_arguments()
    seed_repository: Path = arguments.seed_repository or Path(get_seed_data_repo_path())
    output_directory: Path = arguments.output_directory or (
        seed_repository / STATION_THRESHOLDS_DIRECTORY
    )
    output_directory.mkdir(parents=True, exist_ok=True)

    for region in sorted(
        {HYDROBASINS_REGIONS[country] for country in arguments.countries}
    ):
        # Stations of all countries in the region, so a trace also stops at a
        # station across the border.
        region_countries = sorted(
            country for country, value in HYDROBASINS_REGIONS.items() if value == region
        )
        station_points = {
            country: load_station_points(seed_repository, country)
            for country in region_countries
        }
        basins = load_basins(arguments.basins_directory, region, HYDROBASINS_LEVEL)
        basin_chains = trace_station_basins(
            station_points={
                station_code: point
                for points in station_points.values()
                for station_code, point in points.items()
            },
            basins=basins,
            downstream_distance_km=DOWNSTREAM_DISTANCE_KM,
        )

        for country in region_countries:
            if country not in arguments.countries:
                continue
            spatial_extents = build_spatial_extents(
                station_codes=list(station_points[country]),
                basin_chains=basin_chains,
                basins=basins,
                country_outline=load_country_outline(seed_repository, country),
            )
            output_path = (
                output_directory / f"{country}_station_spatial_extents.geojson"
            )
            write_spatial_extents(spatial_extents, output_path)
            without_extent = sorted(
                set(station_points[country])
                - {spatial_extent.station_code for spatial_extent in spatial_extents}
            )
            print(
                f"{country}: {len(spatial_extents)} of {len(station_points[country])} "
                f"stations written to {output_path}"
                + (
                    f"; no spatial extent for {', '.join(without_extent)}"
                    if without_extent
                    else ""
                )
            )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--countries",
        nargs="+",
        default=sorted(HYDROBASINS_REGIONS),
        choices=sorted(HYDROBASINS_REGIONS),
    )
    parser.add_argument(
        "--seed-repository",
        type=Path,
        default=None,
        help="Local clone of the seed repo. Default: SEED_DATA_REPO_ROOT in data/.env.",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=None,
        help="Default: the station folder of the seed repo.",
    )
    parser.add_argument(
        "--basins-directory", type=Path, default=DEFAULT_BASINS_DIRECTORY
    )
    return parser.parse_args()


def load_station_points(seed_repository: Path, country: str) -> dict[str, Point]:
    stations = load_unique_stations(
        seed_repository
        / STATION_THRESHOLDS_DIRECTORY
        / f"{country}_station_thresholds.json"
    )
    return {
        station_code: Point(station["lon"], station["lat"])
        for station_code, station in stations.items()
    }


def load_country_outline(seed_repository: Path, country: str) -> BaseGeometry:
    outline = union_geometries(
        [
            get_feature_geometry(feature)
            for feature in load_admin_features(
                seed_repository, country, COUNTRY_OUTLINE_ADMIN_LEVEL
            )
        ]
    )
    if outline is None:
        raise ValueError(f"No country outline for {country}")
    return outline


def load_basins(basins_directory: Path, region: str, level: int) -> dict[int, Basin]:
    shapefile_path = _extract_shapefile(basins_directory, region, level)
    with fiona.open(shapefile_path) as collection:
        return {
            int(feature["properties"]["HYBAS_ID"]): Basin(
                next_down_id=int(feature["properties"]["NEXT_DOWN"]),
                distance_to_river_end_km=float(feature["properties"]["DIST_SINK"]),
                geometry=shape(feature["geometry"]),
            )
            for feature in collection
        }


def _extract_shapefile(basins_directory: Path, region: str, level: int) -> Path:
    """Extract one level from the HydroBASINS archive. The spatial index files in
    the archive (.sbn, .sbx) are left out: GDAL rejects them."""
    stem = f"hybas_{region}_lev{level:02d}_v1c"
    missing = [
        suffix
        for suffix in SHAPEFILE_SUFFIXES
        if not (basins_directory / f"{stem}{suffix}").exists()
    ]
    if missing:
        archive_path = basins_directory / f"hybas_{region}_lev01-12_v1c.zip"
        if not archive_path.exists():
            raise FileNotFoundError(
                f"{archive_path} not found. See README.md for where to download it."
            )
        with zipfile.ZipFile(archive_path) as archive:
            for suffix in missing:
                archive.extract(f"{stem}{suffix}", basins_directory)
    return basins_directory / f"{stem}.shp"


def trace_station_basins(
    station_points: dict[str, Point],
    basins: dict[int, Basin],
    downstream_distance_km: float,
) -> dict[str, list[int]]:
    """Per station, the id of the basin it lies in, followed by the basins
    downstream of it along the river.

    The trace ends at the distance limit, before a basin that holds another
    station, or at the end of the river. Stations in the same basin get the same
    trace. A station outside every basin is left out.
    """
    station_basin_ids = _locate_stations(station_points, basins)
    basin_ids_with_station = set(station_basin_ids.values())

    chains: dict[str, list[int]] = {}
    for station_code, start_id in station_basin_ids.items():
        chain = [start_id]
        current_id = basins[start_id].next_down_id
        while (
            current_id != HYDROBASINS_RIVER_END
            and current_id in basins
            and current_id not in basin_ids_with_station
            and basins[start_id].distance_to_river_end_km
            - basins[current_id].distance_to_river_end_km
            <= downstream_distance_km
        ):
            chain.append(current_id)
            current_id = basins[current_id].next_down_id
        chains[station_code] = chain
    return chains


def _locate_stations(
    station_points: dict[str, Point], basins: dict[int, Basin]
) -> dict[str, int]:
    basin_ids = list(basins)
    tree = shapely.STRtree([basins[basin_id].geometry for basin_id in basin_ids])
    station_codes = list(station_points)
    point_indices, basin_indices = tree.query(
        [station_points[station_code] for station_code in station_codes],
        predicate="within",
    )
    located: dict[str, int] = {}
    for point_index, basin_index in zip(point_indices, basin_indices, strict=True):
        # A point on a shared edge is within both basins; the first one is kept.
        located.setdefault(station_codes[int(point_index)], basin_ids[int(basin_index)])
    return located


def build_spatial_extents(
    station_codes: list[str],
    basin_chains: dict[str, list[int]],
    basins: dict[int, Basin],
    country_outline: BaseGeometry,
) -> list[StationSpatialExtent]:
    """The traced basins of each station as one geometry inside the country.
    A station without basins, or whose basins lie outside the country, is left out."""
    spatial_extents: list[StationSpatialExtent] = []
    for station_code in sorted(station_codes):
        chain = basin_chains.get(station_code)
        if chain is None:
            continue
        geometry = _clip_to_country(
            shapely.union_all([basins[basin_id].geometry for basin_id in chain]),
            country_outline,
        )
        if geometry is None:
            continue
        spatial_extents.append(
            StationSpatialExtent(
                station_code=station_code, hydrobasins_ids=chain, geometry=geometry
            )
        )
    return spatial_extents


def _clip_to_country(
    geometry: BaseGeometry, country_outline: BaseGeometry
) -> BaseGeometry | None:
    # Cutting the outline to the bounding box first keeps the intersection fast
    # for countries with a long coastline.
    nearby_outline = shapely.clip_by_rect(country_outline, *geometry.bounds)
    inside = _keep_polygons(geometry.intersection(shapely.make_valid(nearby_outline)))
    if inside is None:
        return None
    simplified = shapely.set_precision(
        inside.simplify(SIMPLIFY_TOLERANCE_DEGREES), COORDINATE_PRECISION_DEGREES
    )
    return _keep_polygons(shapely.make_valid(simplified))


def _keep_polygons(geometry: BaseGeometry) -> BaseGeometry | None:
    """An intersection can leave lines and points behind; a spatial extent is an area."""
    polygons = [
        part
        for part in shapely.get_parts(geometry)
        if isinstance(part, Polygon) and not part.is_empty
    ]
    if not polygons:
        return None
    return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)


def write_spatial_extents(
    spatial_extents: list[StationSpatialExtent], output_path: Path
) -> None:
    """Write a GeoJSON FeatureCollection with one station per line, so a change to
    one station shows up as one changed line."""
    features = [
        json.dumps(
            {
                "type": "Feature",
                "properties": {
                    "station_code": spatial_extent.station_code,
                    "hydrobasins_level": HYDROBASINS_LEVEL,
                    "hydrobasins_ids": spatial_extent.hydrobasins_ids,
                },
                "geometry": mapping(spatial_extent.geometry),
            },
            separators=(",", ":"),
        )
        for spatial_extent in spatial_extents
    ]
    output_path.write_text(
        '{"type":"FeatureCollection","features":[\n' + ",\n".join(features) + "\n]}\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
