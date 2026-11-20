import numpy as np
import pytest
from analysis.drought_hindcast.calculate_alerts import (
    calculate_cell_shares_of_dry_members,
    calculate_leave_one_out_quantiles,
    calculate_region_season,
    calculate_share_of_members_below,
    RegionRainfall,
    Row,
)
from analysis.drought_hindcast.definitions import (
    ForecastVariant,
    LEAD_MONTH_COUNT,
    REFERENCE_LAST_YEAR,
    RegionSeason,
)
from analysis.drought_hindcast.study_area import FIRST_YEAR

MONTHS_PER_YEAR = 12
YEAR_COUNT = REFERENCE_LAST_YEAR - FIRST_YEAR + 3
MEMBER_COUNT = 4
MEAN_MEMBER_OFFSET_MM = 1.5
OND = RegionSeason("KEN", "National", "OND", (10, 11, 12))
OCTOBER_MM, NOVEMBER_MM, DECEMBER_MM = 110, 111, 112
DRY_YEAR = FIRST_YEAR + 5
DRY_YEAR_REDUCTION_MM = 50


def test_forecast_covers_the_season_months_from_the_run_month() -> None:
    # Arrange
    rainfall = _make_rainfall()

    # Act
    _, forecast_rows = calculate_region_season(OND, rainfall)

    # Assert
    row = _find_row(forecast_rows, FIRST_YEAR + 1, months_until_season_start=2)
    assert row["run_month"] == 8
    assert row["forecast_month_count"] == 3
    assert row["ensemble_mean_mm"] == pytest.approx(
        OCTOBER_MM + NOVEMBER_MM + DECEMBER_MM + 3 * MEAN_MEMBER_OFFSET_MM
    )


def test_forecast_drops_season_months_beyond_the_last_lead() -> None:
    # Arrange
    rainfall = _make_rainfall()

    # Act
    _, forecast_rows = calculate_region_season(OND, rainfall)

    # Assert
    row = _find_row(forecast_rows, FIRST_YEAR + 1, months_until_season_start=4)
    assert row["run_month"] == 6
    assert row["forecast_month_count"] == 2
    assert row["ensemble_mean_mm"] == pytest.approx(
        OCTOBER_MM + NOVEMBER_MM + 2 * MEAN_MEMBER_OFFSET_MM
    )


def test_run_within_season_combines_past_months_with_rest_of_season() -> None:
    # Arrange
    rainfall = _make_rainfall()
    observed_shortfall_mm = 10
    rainfall.observed[:] -= observed_shortfall_mm
    season_year = FIRST_YEAR + 1
    rest_of_season_mm = NOVEMBER_MM + DECEMBER_MM + 2 * MEAN_MEMBER_OFFSET_MM

    # Act
    _, forecast_rows = calculate_region_season(OND, rainfall)

    # Assert
    rest_of_season = _find_row(forecast_rows, season_year, -1)
    earlier_forecast = _find_row(
        forecast_rows,
        season_year,
        -1,
        ForecastVariant.EARLIER_FORECAST_FOR_PAST_MONTHS,
    )
    observed = _find_row(
        forecast_rows, season_year, -1, ForecastVariant.OBSERVED_FOR_PAST_MONTHS
    )
    assert rest_of_season["run_month"] == 11
    assert rest_of_season["past_month_count"] == 1
    assert rest_of_season["ensemble_mean_mm"] == pytest.approx(rest_of_season_mm)
    assert earlier_forecast["ensemble_mean_mm"] == pytest.approx(
        rest_of_season_mm + OCTOBER_MM + MEAN_MEMBER_OFFSET_MM
    )
    assert observed["ensemble_mean_mm"] == pytest.approx(
        rest_of_season_mm + OCTOBER_MM - observed_shortfall_mm
    )


def test_dry_year_alerts_and_is_observed_drought() -> None:
    # Arrange
    rainfall = _make_rainfall()
    normal_season_mm = OCTOBER_MM + NOVEMBER_MM + DECEMBER_MM
    dry_season_mm = normal_season_mm - 3 * DRY_YEAR_REDUCTION_MM

    # Act
    observed_rows, forecast_rows = calculate_region_season(OND, rainfall)

    # Assert
    dry_row = _find_row(forecast_rows, DRY_YEAR, months_until_season_start=1)
    normal_row = _find_row(forecast_rows, DRY_YEAR + 1, months_until_season_start=1)
    assert dry_row["probability_below_lower_tercile"] == 1
    assert dry_row["alert_at_probability_0.6"] is True
    assert dry_row["area_share_in_drought_extent"] == 1
    assert dry_row["alert_area_rule"] is True
    assert dry_row["observed_rainfall_mm"] == pytest.approx(dry_season_mm)
    assert dry_row["observed_drought_driest_fifth"] is True
    assert normal_row["alert_at_probability_0.4"] is False
    assert normal_row["alert_area_rule"] is False
    # Each year is left out of its own reference: only the normal year sees the dry one.
    assert dry_row["reference_minimum_mm"] == pytest.approx(normal_season_mm)
    assert normal_row["reference_minimum_mm"] == pytest.approx(dry_season_mm)
    observed_dry_season = next(
        row for row in observed_rows if row["season_year"] == DRY_YEAR
    )
    assert observed_dry_season["observed_rainfall_mm"] == pytest.approx(dry_season_mm)


def test_cell_shares_of_dry_members_are_given_per_year_and_cell() -> None:
    # Arrange
    rainfall = _make_rainfall()

    # Act
    season_years, cell_shares = calculate_cell_shares_of_dry_members(
        OND, rainfall, months_until_season_start=1
    )

    # Assert
    assert cell_shares.shape == (len(season_years), len(rainfall.cell_weights))
    assert cell_shares[season_years == DRY_YEAR][0].tolist() == [1, 1]


def test_years_after_the_hindcast_are_scored_but_not_in_the_reference() -> None:
    # Arrange
    rainfall = _make_rainfall()
    forecast_year = REFERENCE_LAST_YEAR + 1
    september_index = (forecast_year - FIRST_YEAR) * MONTHS_PER_YEAR + 8
    extra_rainfall_mm = 1000
    rainfall.forecast[september_index] += extra_rainfall_mm
    wettest_member_season_mm = (
        OCTOBER_MM + NOVEMBER_MM + DECEMBER_MM + 3 * (MEMBER_COUNT - 1)
    )

    # Act
    _, forecast_rows = calculate_region_season(OND, rainfall)

    # Assert
    forecast_year_row = _find_row(forecast_rows, forecast_year, 1)
    hindcast_year_row = _find_row(forecast_rows, REFERENCE_LAST_YEAR, 1)
    assert forecast_year_row["ensemble_mean_mm"] == pytest.approx(
        OCTOBER_MM
        + NOVEMBER_MM
        + DECEMBER_MM
        + 3 * (MEAN_MEMBER_OFFSET_MM + extra_rainfall_mm)
    )
    assert forecast_year_row["probability_below_lower_tercile"] == 0
    assert hindcast_year_row["reference_maximum_mm"] == pytest.approx(
        wettest_member_season_mm
    )


def test_leave_one_out_quantiles_exclude_the_year_itself() -> None:
    # Arrange
    # Three reference years with two members each, and one later year.
    values = np.array([[0, 1], [10, 11], [20, 21], [99, 99]], dtype=float)[
        :, :, np.newaxis
    ]
    is_reference_year = np.array([True, True, True, False])

    # Act
    minimum, maximum = calculate_leave_one_out_quantiles(
        values, is_reference_year, (0, 1)
    )[:, :, 0]

    # Assert
    assert minimum.tolist() == [10, 0, 0, 0]
    assert maximum.tolist() == [21, 21, 11, 21]


def test_share_of_members_below_ignores_missing_members() -> None:
    # Arrange
    values = np.array([[1, 2, 3, np.nan], [np.nan] * 4])[:, :, np.newaxis]
    thresholds = np.array([[2.5], [2.5]])

    # Act
    shares = calculate_share_of_members_below(values, thresholds)

    # Assert
    assert shares[0, 0] == pytest.approx(2 / 3)
    assert np.isnan(shares[1, 0])


def _make_rainfall() -> RegionRainfall:
    """Every month has 100 mm plus its calendar month number, in both the observations and
    every forecast for it; member m adds m mm. The dry year has less rain in every month.
    """
    month_indices = np.arange(YEAR_COUNT * MONTHS_PER_YEAR)
    # [start month, lead - 1]
    target_month_indices = (
        month_indices[:, np.newaxis] + np.arange(LEAD_MONTH_COUNT)[np.newaxis, :]
    )
    member_offsets = np.arange(MEMBER_COUNT)[np.newaxis, np.newaxis, :, np.newaxis]
    forecast = (
        _get_monthly_rainfall(target_month_indices)[:, :, np.newaxis, np.newaxis]
        + member_offsets
    )
    return RegionRainfall(
        observed=_get_monthly_rainfall(month_indices),
        forecast=np.repeat(forecast, 2, axis=3),
        cell_weights=np.array([1.0, 0.5]),
        cell_latitudes=np.array([0.5, 0.5]),
        cell_longitudes=np.array([36.5, 37.5]),
    )


def _get_monthly_rainfall(month_indices: np.ndarray) -> np.ndarray:
    is_dry_year = month_indices // MONTHS_PER_YEAR == DRY_YEAR - FIRST_YEAR
    return (
        100.0
        + month_indices % MONTHS_PER_YEAR
        + 1
        - np.where(is_dry_year, DRY_YEAR_REDUCTION_MM, 0)
    )


def _find_row(
    rows: list[Row],
    season_year: int,
    months_until_season_start: int,
    variant: ForecastVariant = ForecastVariant.REST_OF_SEASON,
) -> Row:
    return next(
        row
        for row in rows
        if row["season_year"] == season_year
        and row["months_until_season_start"] == months_until_season_start
        and row["variant"] == variant.value
    )
