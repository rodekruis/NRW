"""Recalculate the alert table from the raw files along a separate route, and compare.

Shares the definitions with calculate_alerts but none of its calculation code: regions are
cut out by exact overlap of cell and region instead of by sampling points, and the
forecast is averaged over the region before the months are added up.
"""

import numpy as np
import pandas as pd
import rasterio
import rasterio.mask
import xarray as xr
from analysis.drought_hindcast.definitions import (
    DROUGHT_DEFINITIONS,
    ForecastVariant,
    get_observed_drought_column,
    get_probability_alert_column,
    LEAD_MONTH_COUNT,
    LOWER_TERCILE,
    PROBABILITY_THRESHOLDS,
    REFERENCE_LAST_YEAR,
    REGION_SEASONS,
    RegionSeason,
    RUN_MONTHS_BEFORE_SEASON,
)
from analysis.drought_hindcast.study_area import (
    CHIRPS_DIRECTORY,
    FIRST_YEAR,
    FORECAST_ALERTS_FILE,
    load_region_geometries,
    OBSERVED_SEASONS_FILE,
    SEAS5_DIRECTORY,
)
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry

MONTHS_PER_YEAR = 12
SECONDS_PER_DAY = 86400
MILLIMETRES_PER_METRE = 1000
KEY_COLUMNS = ["region_season", "season_year", "months_until_season_start"]


def main() -> None:
    regions = {
        region_key: shape(geometry)
        for region_key, geometry in load_region_geometries().items()
    }
    _compare_observed(_recalculate_observed(regions))
    _compare_forecast(_recalculate_forecast(regions))


def _recalculate_observed(regions: dict[str, BaseGeometry]) -> pd.DataFrame:
    monthly = _read_observed_region_rainfall(regions)
    rows = []
    for region_season in REGION_SEASONS:
        region_rainfall = monthly[region_season.region_key]
        for season_year in range(FIRST_YEAR, region_rainfall.index.max().year + 1):
            season_months = _get_season_months(region_season, season_year)
            if season_months.isin(region_rainfall.index).all():
                rows.append(
                    {
                        "region_season": region_season.name,
                        "season_year": season_year,
                        "observed_rainfall_mm": region_rainfall[season_months].sum(),
                    }
                )
    seasons = pd.DataFrame(rows)
    for definition_name, share_of_years in DROUGHT_DEFINITIONS.items():
        thresholds = seasons.groupby("region_season")["observed_rainfall_mm"].transform(
            "quantile", share_of_years
        )
        seasons[get_observed_drought_column(definition_name)] = (
            seasons["observed_rainfall_mm"] <= thresholds
        )
    return seasons


def _read_observed_region_rainfall(regions: dict[str, BaseGeometry]) -> pd.DataFrame:
    """Region-average rainfall per month, over the pixels with their centre in the region."""
    rows = []
    for path in sorted(CHIRPS_DIRECTORY.glob("*.tif")):
        year, month = path.stem.split(".")[-2:]
        row: dict[str, float | pd.Period] = {"month": pd.Period(f"{year}-{month}")}
        with rasterio.open(path) as source:
            for region_key, region in regions.items():
                pixels, transform = rasterio.mask.mask(
                    source, [region], crop=True, filled=False
                )
                latitudes = (
                    transform.f + (np.arange(pixels.shape[1]) + 0.5) * transform.e
                )
                pixel_areas = np.cos(np.radians(latitudes))[:, np.newaxis]
                row[region_key] = float(
                    np.ma.average(
                        pixels[0], weights=np.broadcast_to(pixel_areas, pixels[0].shape)
                    )
                )
        rows.append(row)
    return pd.DataFrame(rows).set_index("month")


def _recalculate_forecast(regions: dict[str, BaseGeometry]) -> pd.DataFrame:
    region_rainfall = _read_forecast_region_rainfall(regions)
    rows = []
    for region_season in REGION_SEASONS:
        for months_until_season_start in range(RUN_MONTHS_BEFORE_SEASON + 1):
            rows.extend(
                _recalculate_lead_time(
                    region_season,
                    months_until_season_start,
                    region_rainfall[region_season.region_key],
                )
            )
    return pd.DataFrame(rows)


def _read_forecast_region_rainfall(
    regions: dict[str, BaseGeometry],
) -> dict[str, xr.DataArray]:
    """Region-average rainfall in mm per month, as [start, lead, member] per region."""
    yearly: dict[str, list[xr.DataArray]] = {region_key: [] for region_key in regions}
    for path in sorted(SEAS5_DIRECTORY.glob("*.grib")):
        rate = xr.open_dataset(
            path,
            engine="cfgrib",
            backend_kwargs={"time_dims": ("forecastMonth", "time"), "indexpath": ""},
        )["tprate"].load()
        starts = pd.PeriodIndex(rate["time"].values, freq="M")
        seconds = xr.DataArray(
            [
                [
                    (start + int(lead) - 1).days_in_month * SECONDS_PER_DAY
                    for lead in rate["forecastMonth"].values
                ]
                for start in starts
            ],
            dims=("time", "forecastMonth"),
        )
        rainfall = rate * seconds * MILLIMETRES_PER_METRE
        for region_key, region in regions.items():
            weights = _get_overlap_weights(region, rate["latitude"], rate["longitude"])
            yearly[region_key].append(
                rainfall.weighted(weights)
                .mean(("latitude", "longitude"))
                .assign_coords(time=starts.astype(str))
            )
        print(f"Read {path.name}")
    return {
        region_key: xr.concat(parts, dim="time", join="outer")
        for region_key, parts in yearly.items()
    }


def _get_overlap_weights(
    region: BaseGeometry, latitudes: xr.DataArray, longitudes: xr.DataArray
) -> xr.DataArray:
    """Per grid cell: the area of its overlap with the region."""
    half_cell = abs(float(latitudes[1] - latitudes[0])) / 2
    return xr.DataArray(
        [
            [
                region.intersection(
                    box(
                        longitude - half_cell,
                        latitude - half_cell,
                        longitude + half_cell,
                        latitude + half_cell,
                    )
                ).area
                * np.cos(np.radians(latitude))
                for longitude in longitudes.values
            ]
            for latitude in latitudes.values
        ],
        coords={"latitude": latitudes, "longitude": longitudes},
    )


def _recalculate_lead_time(
    region_season: RegionSeason,
    months_until_season_start: int,
    region_rainfall: xr.DataArray,
) -> list[dict[str, str | int | float]]:
    """Per season year: the ensemble mean and the share of members in the driest third."""
    # [season year][member]
    member_totals: dict[int, np.ndarray] = {}
    run_years: dict[int, int] = {}
    last_run_year = pd.Period(str(region_rainfall["time"].values[-1])).year
    for season_year in range(FIRST_YEAR, last_run_year + 2):
        season_months = _get_season_months(region_season, season_year)
        run_month = season_months[0] - months_until_season_start
        if str(run_month) not in region_rainfall["time"].values:
            continue
        # Lead 1 is the run month itself.
        leads = [
            lead
            for lead in (season_months.asi8 - run_month.ordinal + 1).tolist()
            if lead <= LEAD_MONTH_COUNT
        ]
        totals = (
            region_rainfall.sel(time=str(run_month), forecastMonth=leads)
            .sum("forecastMonth", skipna=False)
            .values
        )
        member_totals[season_year] = totals[~np.isnan(totals)]
        run_years[season_year] = run_month.year

    reference_years = [
        season_year
        for season_year, run_year in run_years.items()
        if run_year <= REFERENCE_LAST_YEAR
    ]
    rows = []
    for season_year, totals in member_totals.items():
        reference = np.concatenate(
            [member_totals[year] for year in reference_years if year != season_year]
        )
        lower_tercile = np.quantile(reference, LOWER_TERCILE)
        rows.append(
            {
                "region_season": region_season.name,
                "season_year": season_year,
                "months_until_season_start": months_until_season_start,
                "ensemble_mean_mm": float(totals.mean()),
                "probability_below_lower_tercile": float(
                    (totals < lower_tercile).mean()
                ),
            }
        )
    return rows


def _get_season_months(region_season: RegionSeason, season_year: int) -> pd.PeriodIndex:
    first_month = pd.Period(year=season_year, month=region_season.months[0], freq="M")
    return pd.period_range(first_month, periods=len(region_season.months), freq="M")


def _compare_observed(recalculated: pd.DataFrame) -> None:
    keys = ["region_season", "season_year"]
    both = pd.read_csv(OBSERVED_SEASONS_FILE).merge(
        recalculated,
        on=keys,
        how="outer",
        suffixes=("", "_recalculated"),
        indicator=True,
    )
    print(f"Observed seasons: {len(both)}, in both: {(both['_merge'] == 'both').sum()}")
    _print_relative_difference(both, "observed_rainfall_mm")
    for definition_name in DROUGHT_DEFINITIONS:
        column = get_observed_drought_column(definition_name)
        is_different = both[column] != both[f"{column}_recalculated"]
        print(f"  {column}: {is_different.sum()} of {len(both)} differ")


def _compare_forecast(recalculated: pd.DataFrame) -> None:
    alerts = pd.read_csv(FORECAST_ALERTS_FILE)
    alerts = alerts.loc[
        (alerts["variant"] == ForecastVariant.REST_OF_SEASON.value)
        & (alerts["months_until_season_start"] >= 0)
    ]
    both = alerts.merge(
        recalculated,
        on=KEY_COLUMNS,
        how="outer",
        suffixes=("", "_recalculated"),
        indicator=True,
    )
    print(f"Forecasts: {len(both)}, in both: {(both['_merge'] == 'both').sum()}")
    _print_relative_difference(both, "ensemble_mean_mm")
    member_difference = (
        (
            both["probability_below_lower_tercile"]
            - both["probability_below_lower_tercile_recalculated"]
        )
        * both["member_count"]
    ).round()
    print("  Members in the driest third, table minus recalculated:")
    print(member_difference.value_counts().sort_index().to_string())
    for threshold in PROBABILITY_THRESHOLDS:
        is_different = both[get_probability_alert_column(threshold)] != (
            both["probability_below_lower_tercile_recalculated"] >= threshold
        )
        print(
            f"  Alerts at {threshold:.0%}: {is_different.sum()} of {len(both)} differ"
        )


def _print_relative_difference(both: pd.DataFrame, column: str) -> None:
    difference = (both[f"{column}_recalculated"] / both[column] - 1).abs()
    print(
        f"  {column}: median difference {difference.median():.2%}, "
        f"largest {difference.max():.2%}"
    )


if __name__ == "__main__":
    main()
