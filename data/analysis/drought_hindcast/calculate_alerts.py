"""Calculate observed season rainfall and SEAS5 drought alerts per region-season, year and run month."""

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import xarray as xr
from analysis.drought_hindcast.definitions import (
    AREA_RULE_ALERT_COLUMN,
    AREA_RULE_MINIMUM_AREA_SHARE,
    AREA_RULE_MINIMUM_PROBABILITY,
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
    UPPER_TERCILE,
)
from analysis.drought_hindcast.study_area import (
    FIRST_YEAR,
    FORECAST_ALERTS_FILE,
    FORECAST_RAINFALL_FILE,
    OBSERVED_RAINFALL_FILE,
    OBSERVED_SEASONS_FILE,
)

MONTHS_PER_YEAR = 12
RAINFALL_DECIMALS = 1
SHARE_DECIMALS = 3
REFERENCE_QUANTILES = (0, LOWER_TERCILE, UPPER_TERCILE, 1)

Row = dict[str, str | int | float | bool | None]


@dataclass(frozen=True)
class RegionRainfall:
    """Monthly rainfall in mm. Month indices count from January of FIRST_YEAR."""

    # [month index]
    observed: np.ndarray
    # [start month index, lead - 1, member, cell]
    forecast: np.ndarray
    # [cell]
    cell_weights: np.ndarray
    # [cell], centres in degrees
    cell_latitudes: np.ndarray
    cell_longitudes: np.ndarray


def main() -> None:
    rainfall_by_region = load_rainfall()
    observed_rows: list[Row] = []
    forecast_rows: list[Row] = []
    for region_season in REGION_SEASONS:
        region_observed_rows, region_forecast_rows = calculate_region_season(
            region_season, rainfall_by_region[region_season.region_key]
        )
        observed_rows.extend(region_observed_rows)
        forecast_rows.extend(region_forecast_rows)
        print(
            f"{region_season.name}: {len(region_observed_rows)} observed seasons, "
            f"{len(region_forecast_rows)} forecast rows"
        )
    _write_rows(observed_rows, OBSERVED_SEASONS_FILE)
    _write_rows(forecast_rows, FORECAST_ALERTS_FILE)


def calculate_region_season(
    region_season: RegionSeason, rainfall: RegionRainfall
) -> tuple[list[Row], list[Row]]:
    """Observed season rows and forecast rows; a season year is the year of its first month."""
    season_years, first_month_indices = _get_season_starts(region_season, rainfall)
    season_month_count = len(region_season.months)

    observed_totals = np.sum(
        [
            _take_months(rainfall.observed, first_month_indices + month_offset)
            for month_offset in range(season_month_count)
        ],
        axis=0,
    )
    observed_columns_by_year = _build_observed_columns(observed_totals)

    observed_rows: list[Row] = [
        {
            "region_season": region_season.name,
            "season_year": int(season_year),
            **observed_columns,
        }
        for season_year, observed_columns in zip(
            season_years, observed_columns_by_year, strict=True
        )
        if observed_columns["observed_rainfall_mm"] is not None
    ]

    forecast_rows: list[Row] = []
    for run_offset in range(-RUN_MONTHS_BEFORE_SEASON, season_month_count):
        forecast_rows.extend(
            _calculate_run_month(
                region_season,
                rainfall,
                season_years,
                first_month_indices,
                run_offset,
                observed_columns_by_year,
            )
        )
    return observed_rows, forecast_rows


def calculate_cell_shares_of_dry_members(
    region_season: RegionSeason,
    rainfall: RegionRainfall,
    months_until_season_start: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Season years and, as [year, cell], the share of members below each cell's own lower
    tercile: the input of the area rule.
    """
    season_years, first_month_indices = _get_season_starts(region_season, rainfall)
    run_offset = -months_until_season_start
    run_month_indices = first_month_indices + run_offset
    cell_totals = _calculate_cell_totals(
        rainfall,
        run_month_indices,
        run_offset,
        _get_forecast_month_offsets(run_offset, len(region_season.months)),
    )
    return season_years, _calculate_cell_shares_of_dry_members(
        cell_totals, _get_run_years(run_month_indices) <= REFERENCE_LAST_YEAR
    )


def _get_season_starts(
    region_season: RegionSeason, rainfall: RegionRainfall
) -> tuple[np.ndarray, np.ndarray]:
    """Per season: its year and the index of its first month."""
    # One year beyond the data, for runs ahead of a season that starts next year.
    year_count = len(rainfall.observed) // MONTHS_PER_YEAR + 2
    season_years = FIRST_YEAR + np.arange(year_count)
    first_month_indices = (
        np.arange(year_count) * MONTHS_PER_YEAR + region_season.months[0] - 1
    )
    return season_years, first_month_indices


def _build_observed_columns(observed_totals: np.ndarray) -> list[Row]:
    is_observed = ~np.isnan(observed_totals)
    columns_by_year: list[Row] = [
        {"observed_rainfall_mm": _round(total, RAINFALL_DECIMALS)}
        for total in observed_totals
    ]
    for definition_name, share_of_years in DROUGHT_DEFINITIONS.items():
        threshold = np.quantile(observed_totals[is_observed], share_of_years)
        for columns, total in zip(columns_by_year, observed_totals, strict=True):
            columns[get_observed_drought_column(definition_name)] = (
                None if np.isnan(total) else bool(total <= threshold)
            )
    return columns_by_year


def _calculate_run_month(
    region_season: RegionSeason,
    rainfall: RegionRainfall,
    season_years: np.ndarray,
    first_month_indices: np.ndarray,
    run_offset: int,
    observed_columns_by_year: list[Row],
) -> list[Row]:
    """Rows for the forecasts that start run_offset months after the first season month."""
    season_month_count = len(region_season.months)
    run_month_indices = first_month_indices + run_offset
    past_month_offsets = range(max(run_offset, 0))
    forecast_month_offsets = _get_forecast_month_offsets(run_offset, season_month_count)
    cell_totals = _calculate_cell_totals(
        rainfall, run_month_indices, run_offset, forecast_month_offsets
    )
    # [year, member]
    rest_of_season = _average_over_region(cell_totals, rainfall.cell_weights)
    values_by_variant = {ForecastVariant.REST_OF_SEASON: rest_of_season}
    if past_month_offsets:
        # Each past month from the forecast that started in that month.
        earlier_forecast = np.sum(
            [
                _average_over_region(
                    _take_months(
                        rainfall.forecast[:, 0], first_month_indices + month_offset
                    ),
                    rainfall.cell_weights,
                )
                for month_offset in past_month_offsets
            ],
            axis=0,
        )
        observed = np.sum(
            [
                _take_months(rainfall.observed, first_month_indices + month_offset)
                for month_offset in past_month_offsets
            ],
            axis=0,
        )
        values_by_variant[ForecastVariant.EARLIER_FORECAST_FOR_PAST_MONTHS] = (
            rest_of_season + earlier_forecast
        )
        values_by_variant[ForecastVariant.OBSERVED_FOR_PAST_MONTHS] = (
            rest_of_season + observed[:, np.newaxis]
        )

    run_years = _get_run_years(run_month_indices)
    is_reference_year = run_years <= REFERENCE_LAST_YEAR
    area_shares = _calculate_area_share_in_drought_extent(
        cell_totals, is_reference_year, rainfall.cell_weights
    )

    rows: list[Row] = []
    for variant, values in values_by_variant.items():
        minimum, lower_tercile, upper_tercile, maximum = (
            calculate_leave_one_out_quantiles(
                values[:, :, np.newaxis], is_reference_year, REFERENCE_QUANTILES
            )[:, :, 0]
        )
        probabilities = calculate_share_of_members_below(
            values[:, :, np.newaxis], lower_tercile[:, np.newaxis]
        )[:, 0]
        member_counts = (~np.isnan(values)).sum(axis=1)
        for year_position in np.flatnonzero(~np.isnan(probabilities)):
            probability = probabilities[year_position]
            row: Row = {
                "region_season": region_season.name,
                "season_year": int(season_years[year_position]),
                "run_year": int(run_years[year_position]),
                "run_month": int(run_month_indices[year_position] % MONTHS_PER_YEAR)
                + 1,
                "months_until_season_start": -run_offset,
                "variant": variant.value,
                "season_month_count": season_month_count,
                "past_month_count": len(past_month_offsets),
                "forecast_month_count": len(forecast_month_offsets),
                "member_count": int(member_counts[year_position]),
                "ensemble_mean_mm": _round(
                    np.nanmean(values[year_position]), RAINFALL_DECIMALS
                ),
                "reference_minimum_mm": _round(
                    minimum[year_position], RAINFALL_DECIMALS
                ),
                "lower_tercile_mm": _round(
                    lower_tercile[year_position], RAINFALL_DECIMALS
                ),
                "upper_tercile_mm": _round(
                    upper_tercile[year_position], RAINFALL_DECIMALS
                ),
                "reference_maximum_mm": _round(
                    maximum[year_position], RAINFALL_DECIMALS
                ),
                "probability_below_lower_tercile": _round(probability, SHARE_DECIMALS),
            }
            for threshold in PROBABILITY_THRESHOLDS:
                row[get_probability_alert_column(threshold)] = bool(
                    probability >= threshold
                )
            if variant == ForecastVariant.REST_OF_SEASON:
                area_share = area_shares[year_position]
                row["area_share_in_drought_extent"] = _round(area_share, SHARE_DECIMALS)
                row[AREA_RULE_ALERT_COLUMN] = bool(
                    area_share >= AREA_RULE_MINIMUM_AREA_SHARE
                )
            else:
                row["area_share_in_drought_extent"] = None
                row[AREA_RULE_ALERT_COLUMN] = None
            rows.append({**row, **observed_columns_by_year[year_position]})
    return rows


def _get_forecast_month_offsets(run_offset: int, season_month_count: int) -> list[int]:
    """Season months that have not passed and are within reach of the forecast."""
    return [
        month_offset
        for month_offset in range(max(run_offset, 0), season_month_count)
        if month_offset - run_offset < LEAD_MONTH_COUNT
    ]


def _calculate_cell_totals(
    rainfall: RegionRainfall,
    run_month_indices: np.ndarray,
    run_offset: int,
    forecast_month_offsets: list[int],
) -> np.ndarray:
    """Forecast rainfall summed over the season months, as [year, member, cell]."""
    return np.sum(
        [
            _take_months(
                rainfall.forecast[:, month_offset - run_offset], run_month_indices
            )
            for month_offset in forecast_month_offsets
        ],
        axis=0,
    )


def _get_run_years(run_month_indices: np.ndarray) -> np.ndarray:
    return FIRST_YEAR + run_month_indices // MONTHS_PER_YEAR


def _calculate_area_share_in_drought_extent(
    cell_totals: np.ndarray, is_reference_year: np.ndarray, cell_weights: np.ndarray
) -> np.ndarray:
    """Share of the region, per year, where enough members are below the cell's own lower tercile."""
    is_in_drought_extent = (
        _calculate_cell_shares_of_dry_members(cell_totals, is_reference_year)
        >= AREA_RULE_MINIMUM_PROBABILITY
    )
    return (is_in_drought_extent * cell_weights).sum(axis=1) / cell_weights.sum()


def _calculate_cell_shares_of_dry_members(
    cell_totals: np.ndarray, is_reference_year: np.ndarray
) -> np.ndarray:
    """Share of members below each cell's own lower tercile, as [year, cell]."""
    cell_lower_terciles = calculate_leave_one_out_quantiles(
        cell_totals, is_reference_year, (LOWER_TERCILE,)
    )[0]
    return calculate_share_of_members_below(cell_totals, cell_lower_terciles)


def calculate_leave_one_out_quantiles(
    values: np.ndarray, is_reference_year: np.ndarray, quantiles: tuple[float, ...]
) -> np.ndarray:
    """Quantiles of the pooled reference members, leaving out the year they are applied to.

    values is [year, member, unit]; the result is [quantile, year, unit].
    """
    year_count, _, unit_count = values.shape
    result = np.full((len(quantiles), year_count, unit_count), np.nan)
    has_data = ~np.isnan(values).all(axis=(1, 2))
    reference_years = np.flatnonzero(is_reference_year & has_data)
    if reference_years.size < 2:
        return result

    reference = values[reference_years]
    # Members present in every reference year, so that the pool has no gaps.
    is_complete_member = ~np.isnan(reference).any(axis=(0, 2))
    reference = reference[:, is_complete_member]

    result[:] = np.quantile(reference.reshape(-1, unit_count), quantiles, axis=0)[
        :, np.newaxis
    ]
    for position, reference_year in enumerate(reference_years):
        other_years = np.delete(reference, position, axis=0)
        result[:, reference_year] = np.quantile(
            other_years.reshape(-1, unit_count), quantiles, axis=0
        )
    return result


def calculate_share_of_members_below(
    values: np.ndarray, thresholds: np.ndarray
) -> np.ndarray:
    """values is [year, member, unit], thresholds and the result are [year, unit]."""
    member_counts = (~np.isnan(values)).sum(axis=1)
    below_counts = (values < thresholds[:, np.newaxis]).sum(axis=1)
    return np.where(
        (member_counts > 0) & ~np.isnan(thresholds),
        below_counts / np.maximum(member_counts, 1),
        np.nan,
    )


def _average_over_region(
    cell_values: np.ndarray, cell_weights: np.ndarray
) -> np.ndarray:
    return (cell_values * cell_weights).sum(axis=-1) / cell_weights.sum()


def _take_months(monthly_values: np.ndarray, month_indices: np.ndarray) -> np.ndarray:
    """Values for the given month indices, NaN where an index falls outside the data."""
    is_in_data = (month_indices >= 0) & (month_indices < len(monthly_values))
    result = np.full((len(month_indices), *monthly_values.shape[1:]), np.nan)
    result[is_in_data] = monthly_values[month_indices[is_in_data]]
    return result


def _round(value: float, decimals: int) -> float | None:
    return None if np.isnan(value) else round(float(value), decimals)


def load_rainfall() -> dict[str, RegionRainfall]:
    observed = xr.open_dataarray(OBSERVED_RAINFALL_FILE)
    forecast = xr.open_dataset(FORECAST_RAINFALL_FILE)
    observed_month_indices = _to_month_indices(observed["month"].values)
    start_month_indices = _to_month_indices(forecast["start"].values)
    month_count = max(observed_month_indices.max(), start_month_indices.max()) + 1

    forecast_values = forecast["rainfall_mm"].transpose(
        "start", "lead", "member", "cell"
    )
    all_forecasts = np.full((month_count, *forecast_values.shape[1:]), np.nan)
    all_forecasts[start_month_indices] = forecast_values.values

    rainfall_by_region: dict[str, RegionRainfall] = {}
    for region_key in forecast["region"].values:
        cell_weights = forecast["cell_weight"].sel(region=region_key).values
        is_in_region = cell_weights > 0
        region_observed = np.full(month_count, np.nan)
        region_observed[observed_month_indices] = observed.sel(region=region_key).values
        rainfall_by_region[str(region_key)] = RegionRainfall(
            observed=region_observed,
            forecast=all_forecasts[..., is_in_region],
            cell_weights=cell_weights[is_in_region],
            cell_latitudes=forecast["latitude"].values[is_in_region],
            cell_longitudes=forecast["longitude"].values[is_in_region],
        )
    return rainfall_by_region


def _to_month_indices(months: np.ndarray) -> np.ndarray:
    first_month = np.datetime64(f"{FIRST_YEAR}-01", "M")
    return (months.astype("datetime64[M]") - first_month).astype(int)


def _write_rows(rows: list[Row], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {path}")


if __name__ == "__main__":
    main()
