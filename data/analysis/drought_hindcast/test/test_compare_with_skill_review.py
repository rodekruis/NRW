import numpy as np
import pytest
from analysis.drought_hindcast.compare_with_skill_review import (
    calculate_roc_area,
    get_measured_level,
    get_rule_level,
    SkillLevel,
)


def test_roc_area_is_one_when_every_drought_has_more_dry_members() -> None:
    # Arrange
    shares_of_dry_members = np.array([0.8, 0.6, 0.3, 0.2, 0.1])
    is_drought = np.array([True, True, False, False, False])

    # Act
    roc_area, probability_by_chance = calculate_roc_area(
        shares_of_dry_members, is_drought
    )

    # Assert
    assert roc_area == pytest.approx(1)
    # One of the ten ways to pick two years out of five.
    assert probability_by_chance == pytest.approx(1 / 10)


def test_roc_area_is_a_half_when_the_forecast_never_changes() -> None:
    # Arrange
    shares_of_dry_members = np.full(6, 0.4)
    is_drought = np.array([True, True, False, False, False, False])

    # Act
    roc_area, _ = calculate_roc_area(shares_of_dry_members, is_drought)

    # Assert
    assert roc_area == pytest.approx(1 / 2)


@pytest.mark.parametrize(
    ("roc_area", "probability_by_chance", "expected_level"),
    [
        (0.7, 0.01, SkillLevel.INCLUDE),
        (0.7, 0.2, SkillLevel.READINESS),
        (0.55, 0.01, SkillLevel.READINESS),
        (0.5, 0.5, SkillLevel.EXCLUDE),
        (0.4, 0.9, SkillLevel.EXCLUDE),
    ],
)
def test_measured_level_needs_both_size_and_significance_for_include(
    roc_area: float, probability_by_chance: float, expected_level: SkillLevel
) -> None:
    # Act
    level = get_measured_level(roc_area, probability_by_chance)

    # Assert
    assert level == expected_level


@pytest.mark.parametrize(
    ("hit_rate", "alert_frequency", "probability_by_chance", "expected_level"),
    [
        (0.7, 0.3, 0.01, SkillLevel.INCLUDE),
        (0.5, 0.3, 0.2, SkillLevel.READINESS),
        (0.3, 0.3, 0.6, SkillLevel.EXCLUDE),
        (0.2, 0.4, 0.9, SkillLevel.EXCLUDE),
    ],
)
def test_rule_level_compares_hit_rate_with_alerts_unrelated_to_droughts(
    hit_rate: float,
    alert_frequency: float,
    probability_by_chance: float,
    expected_level: SkillLevel,
) -> None:
    # Act
    level = get_rule_level(hit_rate, alert_frequency, probability_by_chance)

    # Assert
    assert level == expected_level
