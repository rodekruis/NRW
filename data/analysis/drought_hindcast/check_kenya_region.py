"""Check what scoring Kenya on its arid and semi-arid counties, instead of the whole
country, does to the observed season rainfall and its rank."""

import numpy as np
import pandas as pd
import rasterio
from analysis.drought_hindcast.build_region_shapes import (
    get_feature_geometry,
    load_admin_features,
)
from analysis.drought_hindcast.definitions import DROUGHT_DEFINITIONS, REGION_SEASONS
from analysis.drought_hindcast.indicator_data import KENYA_REGION_CHECK_FILE
from analysis.drought_hindcast.plot_skill import DEFAULT_DROUGHT_DEFINITION
from analysis.drought_hindcast.prepare_observed_rainfall import (
    CHIRPS_CELL_SIZE_DEGREES,
    CHIRPS_MONTH_PATTERN,
    CHIRPS_SUBCELL_COUNT,
)
from analysis.drought_hindcast.region_weights import calculate_cell_weights
from analysis.drought_hindcast.study_area import CHIRPS_DIRECTORY, load_study_bounds
from shapely import union_all
from shapely.geometry import mapping
from shared.data_helpers import get_seed_data_repo_path

COUNTRY_CODE_ISO3 = "KEN"
COUNTY_ADMIN_LEVEL = 1
COUNTY_NAME_PROPERTY = "ADM1_EN"
# The 23 counties of the National Drought Management Authority, as named in the admin areas.
ARID_COUNTIES = [
    "Baringo",
    "Garissa",
    "Isiolo",
    "Mandera",
    "Marsabit",
    "Samburu",
    "TanaRiver",
    "Turkana",
    "Wajir",
]
SEMI_ARID_COUNTIES = [
    "Embu",
    "Kajiado",
    "Kilifi",
    "Kitui",
    "Kwale",
    "Laikipia",
    "Lamu",
    "Makueni",
    "Meru",
    "Narok",
    "Nyeri",
    "TaitaTaveta",
    "Tharaka-Nithi",
    "WestPokot",
]
NATIONAL = "national"
RAINFALL_DECIMALS = 1


def main() -> None:
    county_geometries = {
        feature["properties"][COUNTY_NAME_PROPERTY]: get_feature_geometry(feature)
        for feature in load_admin_features(
            get_seed_data_repo_path(), COUNTRY_CODE_ISO3, COUNTY_ADMIN_LEVEL
        )
    }
    counties_by_area = {
        NATIONAL: list(county_geometries),
        "arid_and_semi_arid": [*ARID_COUNTIES, *SEMI_ARID_COUNTIES],
        "arid": ARID_COUNTIES,
    }
    bounds = load_study_bounds()
    weights_by_area = {
        area: calculate_cell_weights(
            mapping(union_all([county_geometries[county] for county in counties])),
            bounds,
            CHIRPS_CELL_SIZE_DEGREES,
            CHIRPS_SUBCELL_COUNT,
        )
        for area, counties in counties_by_area.items()
    }
    for area, weights in weights_by_area.items():
        print(
            f"{area}: {len(counties_by_area[area])} counties, "
            f"{weights.sum() / weights_by_area[NATIONAL].sum():.0%} of the country"
        )

    monthly_rainfall = _load_monthly_rainfall(weights_by_area)
    seasons = pd.concat(
        rank_seasons(monthly_rainfall, region_season.months).assign(
            season=region_season.season_name
        )
        for region_season in REGION_SEASONS
        if region_season.country_code_iso3 == COUNTRY_CODE_ISO3
    )
    seasons.to_csv(KENYA_REGION_CHECK_FILE, index=False)
    print(f"Wrote {len(seasons)} rows to {KENYA_REGION_CHECK_FILE}")
    _print_agreement(seasons, list(weights_by_area))


def rank_seasons(
    monthly_rainfall: pd.DataFrame, season_months: tuple[int, ...]
) -> pd.DataFrame:
    """Per season year and area: the season rainfall, its rank from the driest, and
    whether it is a drought. Seasons within one calendar year only.
    """
    season_rainfall = monthly_rainfall.loc[
        monthly_rainfall["month"].isin(season_months)
    ]
    areas = [
        column for column in monthly_rainfall.columns if column not in ("year", "month")
    ]
    totals = season_rainfall.groupby("year")[areas].sum()
    is_complete = season_rainfall.groupby("year")["month"].count() == len(season_months)
    totals = totals.loc[is_complete]

    seasons = pd.DataFrame({"season_year": totals.index})
    drought_share = DROUGHT_DEFINITIONS[DEFAULT_DROUGHT_DEFINITION]
    for area in areas:
        rainfall = totals[area].to_numpy()
        seasons[f"{area}_rainfall_mm"] = rainfall.round(RAINFALL_DECIMALS)
        seasons[f"{area}_rank_from_driest"] = totals[area].rank().astype(int).to_numpy()
        seasons[f"{area}_is_drought"] = rainfall <= np.quantile(rainfall, drought_share)
    return seasons


def _load_monthly_rainfall(weights_by_area: dict[str, np.ndarray]) -> pd.DataFrame:
    rows = []
    for path in sorted(CHIRPS_DIRECTORY.glob("*.tif")):
        match = CHIRPS_MONTH_PATTERN.search(path.name)
        if match is None:
            raise ValueError(f"No year and month in file name {path.name}")
        with rasterio.open(path) as source:
            cell_rainfall = source.read(1, masked=True)
        rows.append(
            {
                "year": int(match.group(1)),
                "month": int(match.group(2)),
                **{
                    area: float(np.ma.average(cell_rainfall, weights=weights))
                    for area, weights in weights_by_area.items()
                },
            }
        )
    return pd.DataFrame(rows)


def _print_agreement(seasons: pd.DataFrame, areas: list[str]) -> None:
    for season, season_rows in seasons.groupby("season", sort=False):
        is_national_drought = season_rows[f"{NATIONAL}_is_drought"]
        for area in areas:
            is_drought = season_rows[f"{area}_is_drought"]
            print(
                f"{season}, {area}: {is_drought.sum()} droughts, "
                f"{(is_drought & is_national_drought).sum()} of them also national; "
                "rainfall correlates "
                f"{season_rows[f'{area}_rainfall_mm'].corr(season_rows[f'{NATIONAL}_rainfall_mm']):.2f}"
                " with national"
            )


if __name__ == "__main__":
    main()
