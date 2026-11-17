import numpy as np
import pandas as pd
import pytest
from analysis.drought_hindcast.combine_indicators import (
    Combination,
    combine_alerts,
    summarise_reliable_lead_times,
)
from analysis.drought_hindcast.indicator_definitions import (
    get_iod_region_seasons,
    Indicator,
    IOD_DROUGHT_PHASES,
)

ALERTS_BY_INDICATOR = {
    Indicator.SEAS5: np.array([True, True, False, False]),
    Indicator.IOD: np.array([True, False, True, False]),
}


def test_either_and_both_combine_the_two_alerts() -> None:
    # Arrange
    indicators_with_skill = [Indicator.SEAS5, Indicator.IOD]

    # Act
    alerts = combine_alerts(ALERTS_BY_INDICATOR, indicators_with_skill)

    # Assert
    assert alerts[Combination.EITHER].tolist() == [True, True, True, False]
    assert alerts[Combination.BOTH].tolist() == [True, False, False, False]


@pytest.mark.parametrize(
    ("indicators_with_skill", "expected_alerts"),
    [
        ([Indicator.SEAS5, Indicator.IOD], [True, False, False, False]),
        ([Indicator.SEAS5], [True, True, False, False]),
        ([Indicator.IOD], [True, False, True, False]),
        ([], [False, False, False, False]),
    ],
)
def test_all_with_skill_needs_an_alert_of_every_indicator_that_has_skill(
    indicators_with_skill: list[Indicator], expected_alerts: list[bool]
) -> None:
    # Arrange
    alerts_by_indicator = ALERTS_BY_INDICATOR

    # Act
    alerts = combine_alerts(alerts_by_indicator, indicators_with_skill)

    # Assert
    assert alerts[Combination.ALL_WITH_SKILL].tolist() == expected_alerts


def test_every_iod_region_season_is_a_defined_region_season() -> None:
    # Arrange
    expected_names = set(IOD_DROUGHT_PHASES)

    # Act
    region_seasons = get_iod_region_seasons()

    # Assert
    assert {region_season.name for region_season in region_seasons} == expected_names


def test_alerts_are_reliable_from_the_forecast_after_the_last_that_fails() -> None:
    # Arrange
    probability_by_chance_by_lead_time = {3: 0.01, 2: 0.2, 1: 0.03, 0: 0.01}
    combinations = pd.DataFrame(
        [
            {
                "scope": "KEN National OND",
                "combination": Combination.EITHER.value,
                "months_until_season_start": months_until_season_start,
                "probability_by_chance": probability_by_chance,
                "hit_count": 10 - months_until_season_start,
                "drought_count": 15,
                "alert_count": 20,
                "hit_rate": 0.6,
                "false_alarm_ratio": 0.5,
            }
            for months_until_season_start, probability_by_chance in (
                probability_by_chance_by_lead_time.items()
            )
        ]
    )

    # Act
    reliable_lead_times = summarise_reliable_lead_times(combinations)

    # Assert
    assert len(reliable_lead_times) == 1
    assert reliable_lead_times["reliable_from_months_before_season"].iloc[0] == 1
    assert reliable_lead_times["hit_count"].iloc[0] == 9
