import numpy as np
import pandas as pd
import pytest
from analysis.drought_hindcast.definitions import get_observed_drought_column
from analysis.drought_hindcast.plot_thresholds import (
    count_dry_members,
    get_minimum_dry_member_counts,
    score_thresholds,
)


def test_dry_members_are_recovered_from_the_rounded_share() -> None:
    # Arrange
    # 28 of 51 members is 0.549, stored as 0.55.
    cases = pd.DataFrame(
        {"probability_below_lower_tercile": [0.55, 0.4], "member_count": [51, 25]}
    )

    # Act
    dry_member_counts = count_dry_members(cases)

    # Assert
    assert dry_member_counts.tolist() == [28, 10]


def test_threshold_is_met_by_exactly_that_share_of_members() -> None:
    # Arrange
    member_counts = np.array([25, 51])

    # Act
    minimum_counts_at_40_percent = get_minimum_dry_member_counts(0.4, member_counts)
    minimum_counts_at_55_percent = get_minimum_dry_member_counts(0.55, member_counts)

    # Assert
    assert minimum_counts_at_40_percent.tolist() == [10, 21]
    assert minimum_counts_at_55_percent.tolist() == [14, 29]


def test_higher_threshold_keeps_only_the_forecasts_with_more_dry_members() -> None:
    # Arrange
    # Two droughts with 60% and 40% of members dry, and one other year with 40%.
    cases = pd.DataFrame(
        {
            "probability_below_lower_tercile": [0.6, 0.4, 0.4],
            "member_count": [25, 25, 25],
            get_observed_drought_column("driest_third"): [True, True, False],
            "season_year": [2000, 2001, 2002],
        }
    )

    # Act
    scores = score_thresholds(
        cases, (0.4, 0.5), np.random.default_rng(seed=1)
    ).set_index("threshold")

    # Assert
    assert scores.loc[0.4, "hit_rate"] == pytest.approx(1)
    assert scores.loc[0.4, "false_alarm_ratio"] == pytest.approx(1 / 3, abs=0.001)
    assert scores.loc[0.5, "hit_rate"] == pytest.approx(1 / 2)
    assert scores.loc[0.5, "false_alarm_ratio"] == pytest.approx(0)
