"""Build one shape per drought region from the seed-data admin areas."""

import json
from pathlib import Path

from analysis.drought_hindcast.study_area import REGIONS_FILE
from data_management.seed_data_management.admin_areas.admin_area_dataset_helpers import (
    get_feature_geometry,
    get_git_revision,
    get_pcode,
    load_admin_features,
)
from data_management.seed_data_management.drought.migrate_drought_region_area_mapping import (
    DEFAULT_ALERT_CONFIGS_FILE,
    DROUGHT_REGION_ADMIN_LEVELS,
    DroughtRegion,
    load_drought_regions,
)
from shapely import union_all
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry
from shared.data_helpers import get_seed_data_repo_path

STUDY_COUNTRIES = ["ETH", "KEN", "ZWE", "LSO"]
NATIONAL_REGION_NAME = "National"
NATIONAL_ADMIN_LEVEL = 0


def main() -> None:
    seed_repo_path = get_seed_data_repo_path()
    regions_by_country = load_drought_regions(DEFAULT_ALERT_CONFIGS_FILE)

    features: list[dict] = []
    for country in STUDY_COUNTRIES:
        regions = regions_by_country.get(country)
        if regions:
            features.extend(_build_region_features(seed_repo_path, country, regions))
        else:
            features.append(_build_national_feature(seed_repo_path, country))

    REGIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with REGIONS_FILE.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "type": "FeatureCollection",
                "seed_data_revision": get_git_revision(seed_repo_path),
                "features": features,
            },
            file,
        )
    print(f"Wrote {len(features)} regions to {REGIONS_FILE}")


def _build_region_features(
    seed_repo_path: Path, country: str, regions: list[DroughtRegion]
) -> list[dict]:
    admin_level = DROUGHT_REGION_ADMIN_LEVELS[country]
    geometry_by_place_code = {
        get_pcode(feature, admin_level): get_feature_geometry(feature)
        for feature in load_admin_features(seed_repo_path, country, admin_level)
    }
    features: list[dict] = []
    for region in regions:
        unknown_place_codes = set(region.place_codes) - set(geometry_by_place_code)
        if unknown_place_codes:
            raise ValueError(
                f"{country} {region.region_name}: place codes not in admin level "
                f"{admin_level}: {sorted(unknown_place_codes)}"
            )
        geometry = union_all(
            [geometry_by_place_code[place_code] for place_code in region.place_codes]
        )
        features.append(
            _build_feature(country, region.region_name, region.place_codes, geometry)
        )
    return features


def _build_national_feature(seed_repo_path: Path, country: str) -> dict:
    geometry = union_all(
        [
            get_feature_geometry(feature)
            for feature in load_admin_features(
                seed_repo_path, country, NATIONAL_ADMIN_LEVEL
            )
        ]
    )
    return _build_feature(country, NATIONAL_REGION_NAME, [], geometry)


def _build_feature(
    country: str, region_name: str, place_codes: list[str], geometry: BaseGeometry
) -> dict:
    west, south, east, north = geometry.bounds
    print(
        f"{country} {region_name}: {len(place_codes)} place codes, "
        f"bounds {west:.2f}, {south:.2f}, {east:.2f}, {north:.2f}"
    )
    return {
        "type": "Feature",
        "properties": {
            "country_code_iso3": country,
            "region_name": region_name,
            "place_codes": place_codes,
        },
        "geometry": mapping(geometry),
    }


if __name__ == "__main__":
    main()
