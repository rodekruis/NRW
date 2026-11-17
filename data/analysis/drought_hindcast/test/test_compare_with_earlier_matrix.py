import numpy as np
import pandas as pd
from analysis.drought_hindcast.compare_with_earlier_matrix import (
    AlertTiming,
    count_outcomes,
    get_alert_column,
    summarise_seasons,
)
from analysis.drought_hindcast.definitions import (
    AREA_RULE_ALERT_COLUMN,
    get_observed_drought_column,
    get_probability_alert_column,
    PROBABILITY_THRESHOLDS,
)

LOWEST_THRESHOLD_RULE = f"probability_{PROBABILITY_THRESHOLDS[0]}"


def test_outcomes_are_counted_per_cell_of_the_matrix() -> None:
    # Arrange
    is_alert = np.array([True, True, True, False, False, False])
    is_drought = np.array([True, True, False, True, False, False])

    # Act
    counts = count_outcomes(is_alert, is_drought)

    # Assert
    assert (counts.hit, counts.false_alarm, counts.miss, counts.correct_negative) == (
        2,
        1,
        1,
        2,
    )
    assert counts.drought_count == 3
    assert counts.alert_count == 3
    assert counts.case_count == 6


def test_season_alerts_at_any_lead_time_but_not_one_month_before() -> None:
    # Arrange
    # One season with an alert three months before only, one with an alert one month before.
    cases = _create_cases(
        season_years=[2000, 2000, 2001, 2001],
        months_until_season_start=[3, 1, 3, 1],
        is_alert=[True, False, False, True],
    )

    # Act
    seasons = summarise_seasons(cases).set_index("season_year")

    # Assert
    any_lead_time = get_alert_column(LOWEST_THRESHOLD_RULE, AlertTiming.ANY_LEAD_TIME)
    one_month_before = get_alert_column(
        LOWEST_THRESHOLD_RULE, AlertTiming.ONE_MONTH_BEFORE
    )
    assert seasons[any_lead_time].tolist() == [True, True]
    assert seasons[one_month_before].tolist() == [False, True]


def test_seasons_are_ranked_from_driest_within_their_region_season() -> None:
    # Arrange
    cases = _create_cases(
        season_years=[2000, 2001, 2002],
        months_until_season_start=[1, 1, 1],
        is_alert=[False, False, False],
        observed_rainfall_mm=[300.0, 100.0, 200.0],
    )

    # Act
    seasons = summarise_seasons(cases).set_index("season_year")

    # Assert
    assert seasons["observed_rank_from_driest"].tolist() == [3, 1, 2]
    assert seasons["observed_season_count"].tolist() == [3, 3, 3]


def _create_cases(
    season_years: list[int],
    months_until_season_start: list[int],
    is_alert: list[bool],
    observed_rainfall_mm: list[float] | None = None,
) -> pd.DataFrame:
    case_count = len(season_years)
    return pd.DataFrame(
        {
            "region_season": "KEN National OND",
            "season_year": season_years,
            "months_until_season_start": months_until_season_start,
            **{
                get_probability_alert_column(threshold): is_alert
                for threshold in PROBABILITY_THRESHOLDS
            },
            AREA_RULE_ALERT_COLUMN: is_alert,
            get_observed_drought_column("driest_third"): [False] * case_count,
            "probability_below_lower_tercile": [0.5] * case_count,
            "area_share_in_drought_extent": [0.5] * case_count,
            "observed_rainfall_mm": observed_rainfall_mm or [100.0] * case_count,
        }
    )
