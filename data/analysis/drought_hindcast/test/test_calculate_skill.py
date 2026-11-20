import numpy as np
import pytest
from analysis.drought_hindcast.calculate_skill import (
    calculate_probability_by_chance,
    calculate_scores,
)


def test_scores_count_hits_against_droughts_and_alerts() -> None:
    # Arrange
    # Four droughts of which three were alerted, and two alerts without a drought.
    is_drought = np.array([True, True, True, True, False, False, False, False])
    is_alert = np.array([True, True, True, False, True, True, False, False])
    season_years = np.arange(2000, 2008)

    # Act
    scores = calculate_scores(
        is_alert, is_drought, season_years, np.random.default_rng(seed=1)
    )

    # Assert
    assert scores["season_count"] == 8
    assert scores["drought_count"] == 4
    assert scores["alert_count"] == 5
    assert scores["hit_count"] == 3
    assert scores["hit_rate"] == pytest.approx(3 / 4)
    assert scores["false_alarm_ratio"] == pytest.approx(2 / 5)
    assert scores["alert_frequency"] == pytest.approx(5 / 8)
    assert scores["drought_frequency"] == pytest.approx(4 / 8)
    assert scores["hit_rate_low"] <= scores["hit_rate"] <= scores["hit_rate_high"]
    assert (
        scores["false_alarm_ratio_low"]
        <= scores["false_alarm_ratio"]
        <= scores["false_alarm_ratio_high"]
    )


def test_cases_in_the_same_year_are_resampled_together() -> None:
    # Arrange
    # Two region-seasons that agree in every year: within a year all cases are hits or none.
    is_drought = np.array([True, True, True, True, True, True])
    is_alert = np.array([True, True, False, False, True, True])
    season_years = np.array([2000, 2000, 2001, 2001, 2002, 2002])

    # Act
    scores = calculate_scores(
        is_alert, is_drought, season_years, np.random.default_rng(seed=1)
    )

    # Assert
    # Resampling single cases would give a narrower range than whole years do.
    assert scores["hit_rate"] == pytest.approx(2 / 3, abs=0.001)
    assert scores["hit_rate_low"] == 0
    assert scores["hit_rate_high"] == 1


def test_false_alarm_ratio_is_missing_without_alerts() -> None:
    # Arrange
    is_drought = np.array([True, False, False])
    is_alert = np.array([False, False, False])
    season_years = np.array([2000, 2001, 2002])

    # Act
    scores = calculate_scores(
        is_alert, is_drought, season_years, np.random.default_rng(seed=1)
    )

    # Assert
    assert scores["hit_rate"] == 0
    assert np.isnan(scores["false_alarm_ratio"])
    assert np.isnan(scores["false_alarm_ratio_low"])


def test_probability_by_chance_counts_random_alerts_with_as_many_hits() -> None:
    # Arrange
    # One alert in four seasons lands on the single drought one time in four.
    season_count = 4

    # Act
    probability = calculate_probability_by_chance(
        hit_count=1, alert_count=1, drought_count=1, season_count=season_count
    )

    # Assert
    assert probability == pytest.approx(1 / season_count)


def test_probability_by_chance_is_certain_without_hits() -> None:
    # Arrange
    hit_count = 0

    # Act
    probability = calculate_probability_by_chance(
        hit_count=hit_count, alert_count=2, drought_count=1, season_count=4
    )

    # Assert
    assert probability == pytest.approx(1)
