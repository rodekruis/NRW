import pandas as pd
import pytest
from analysis.drought_hindcast.compare_with_skill_review import SkillLevel
from analysis.drought_hindcast.plot_threshold_choices import (
    add_evidence_levels,
    EVIDENCE_COLUMN,
    find_alert_starts,
    order_by_alert_start,
)

INCLUDE = SkillLevel.INCLUDE.value
READINESS = SkillLevel.READINESS.value
EXCLUDE = SkillLevel.EXCLUDE.value


def test_evidence_level_follows_the_hits_by_chance_and_the_level_without_skill() -> (
    None
):
    # Arrange
    skill = pd.DataFrame(
        {
            "hit_rate": [0.7, 0.5, 0.3],
            "alert_frequency": [0.4, 0.4, 0.4],
            "probability_by_chance": [0.01, 0.2, 0.8],
        }
    )

    # Act
    levels = add_evidence_levels(skill)

    # Assert
    assert levels[EVIDENCE_COLUMN].tolist() == [INCLUDE, READINESS, EXCLUDE]


@pytest.mark.parametrize(
    ("level_by_lead_time", "expected_alert_from", "expected_advisory_from"),
    [
        # A forecast that stands out while a later one does not is not counted.
        (
            {4: READINESS, 3: INCLUDE, 2: EXCLUDE, 1: INCLUDE, 0: INCLUDE},
            1,
            1,
        ),
        ({2: READINESS, 1: READINESS, 0: INCLUDE}, 0, 2),
        ({1: INCLUDE, 0: READINESS}, None, 1),
        ({1: INCLUDE, 0: EXCLUDE}, None, None),
    ],
)
def test_alerts_start_where_every_later_forecast_stands_out_too(
    level_by_lead_time: dict[int, str],
    expected_alert_from: int | None,
    expected_advisory_from: int | None,
) -> None:
    # Arrange: the levels per lead time are the parameters.

    # Act
    alert_from, advisory_from = find_alert_starts(level_by_lead_time)

    # Assert
    assert alert_from == expected_alert_from
    assert advisory_from == expected_advisory_from


def test_region_seasons_are_ordered_from_the_earliest_alert_to_none() -> None:
    # Arrange
    choices = pd.DataFrame(
        {
            "region_season": ["Late", "None", "Early", "Other threshold", "Not pooled"],
            "is_in_pooled_results": [True, True, True, True, False],
            "threshold": [0.4, 0.4, 0.4, 0.3, 0.4],
            "alert_from_months_before_season": [0, None, 4, 4, 4],
        }
    ).astype({"alert_from_months_before_season": "Int64"})

    # Act
    names = order_by_alert_start(choices, threshold=0.4)

    # Assert
    assert names == ["Early", "Late", "None"]
