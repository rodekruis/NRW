import pandas as pd
from analysis.drought_hindcast.definitions import ForecastVariant
from analysis.drought_hindcast.plot_in_season import select_variant_cases

REST_OF_SEASON = ForecastVariant.REST_OF_SEASON.value
OBSERVED = ForecastVariant.OBSERVED_FOR_PAST_MONTHS.value


def _build_cases() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "months_until_season_start": [1, 0, -1, -1],
            "variant": [REST_OF_SEASON, REST_OF_SEASON, REST_OF_SEASON, OBSERVED],
            "forecast_month_count": [3, 3, 2, 2],
            "past_month_count": [0, 0, 1, 1],
        }
    )


def test_a_variant_shares_the_forecasts_before_the_season_and_counts_its_past_months() -> (
    None
):
    # Arrange
    cases = _build_cases()

    # Act
    selected = select_variant_cases(cases, ForecastVariant.OBSERVED_FOR_PAST_MONTHS)

    # Assert
    assert selected["variant"].tolist() == [REST_OF_SEASON, REST_OF_SEASON, OBSERVED]
    assert selected["forecast_month_count"].tolist() == [3, 3, 3]


def test_the_rest_of_season_variant_keeps_the_months_it_forecasts() -> None:
    # Arrange
    cases = _build_cases()

    # Act
    selected = select_variant_cases(cases, ForecastVariant.REST_OF_SEASON)

    # Assert
    assert selected["variant"].tolist() == [REST_OF_SEASON] * 3
    assert selected["forecast_month_count"].tolist() == [3, 3, 2]
