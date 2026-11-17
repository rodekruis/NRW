import numpy as np
import pandas as pd
import pytest
from analysis.drought_hindcast.calculate_fews_net_alerts import (
    calculate_rank_among_others,
    calculate_run_month_alerts,
    count_season_months,
    CURRENT_SHARE_COLUMN,
    PROJECTED_CHANGE_COLUMN,
    PROJECTION_END_COLUMN,
    PROJECTION_START_COLUMN,
    REPORT_MONTH_COLUMN,
    select_projection,
)
from analysis.drought_hindcast.check_fews_net import score_projections
from analysis.drought_hindcast.prepare_fews_net import CRISIS_OR_WORSE_COLUMN

OCTOBER = 10
SEASON_MONTH_COUNT = 3


def _build_phase(
    report_month: str,
    scenario: str,
    projection_start: str,
    projection_end: str,
    share: float,
) -> dict[str, str | float | pd.Period]:
    return {
        REPORT_MONTH_COLUMN: pd.Period(report_month, freq="M"),
        "scenario": scenario,
        PROJECTION_START_COLUMN: pd.Period(projection_start, freq="M"),
        PROJECTION_END_COLUMN: pd.Period(projection_end, freq="M"),
        CRISIS_OR_WORSE_COLUMN: share,
    }


def test_season_months_of_a_projection_are_the_months_that_both_cover() -> None:
    # Arrange
    projection = pd.Series(_build_phase("2024-08", "ML2", "2024-10", "2025-01", 0.5))
    season_start = pd.Period("2024-12", freq="M")

    # Act
    covered = count_season_months(projection, season_start, SEASON_MONTH_COUNT)
    not_covered = count_season_months(projection, season_start + 12, SEASON_MONTH_COUNT)

    # Assert
    assert covered == 2
    assert not_covered == 0


@pytest.mark.parametrize(
    ("season_start", "expected_scenario"),
    [
        # Most season months: the second projection covers October to December.
        ("2024-10", "ML2"),
        # As many months each (September, and October): the earlier projection.
        ("2024-09", "ML1"),
        # No season month in either: the projection that reaches furthest.
        ("2025-06", "ML2"),
    ],
)
def test_the_projection_that_covers_most_of_the_season_is_selected(
    season_start: str, expected_scenario: str
) -> None:
    # Arrange
    report_projections = pd.DataFrame(
        [
            _build_phase("2024-08", "ML1", "2024-08", "2024-09", 0.1),
            _build_phase("2024-08", "ML2", "2024-10", "2025-01", 0.5),
        ]
    )
    season_month_count = 2 if season_start == "2024-09" else SEASON_MONTH_COUNT

    # Act
    projection = select_projection(
        report_projections, pd.Period(season_start, freq="M"), season_month_count
    )

    # Assert
    assert projection["scenario"] == expected_scenario


def test_a_run_uses_the_latest_report_that_is_old_enough() -> None:
    # Arrange
    region_phases = pd.DataFrame(
        [
            _build_phase("2024-06", "CS", "2024-06", "2024-06", 0.1),
            _build_phase("2024-07", "ML2", "2024-10", "2025-01", 0.3),
            _build_phase("2024-08", "ML2", "2024-10", "2025-01", 0.6),
        ]
    )

    # Act
    # The September run for the season that starts in October.
    share_by_report_lag = {
        report_lag_months: calculate_run_month_alerts(
            region_phases,
            first_season_month=OCTOBER,
            season_month_count=SEASON_MONTH_COUNT,
            months_until_season_start=1,
            report_lag_months=report_lag_months,
        )
        .set_index("season_year")
        .loc[2024]
        for report_lag_months in (1, 2)
    }

    # Assert
    assert share_by_report_lag[1][CRISIS_OR_WORSE_COLUMN] == pytest.approx(0.6)
    assert share_by_report_lag[2][CRISIS_OR_WORSE_COLUMN] == pytest.approx(0.3)
    assert share_by_report_lag[1][CURRENT_SHARE_COLUMN] == pytest.approx(0.1)
    assert share_by_report_lag[1][PROJECTED_CHANGE_COLUMN] == pytest.approx(0.5)


def test_a_season_without_a_recent_report_has_no_run() -> None:
    # Arrange
    region_phases = pd.DataFrame(
        [_build_phase("2024-01", "ML2", "2024-06", "2024-09", 0.3)]
    )

    # Act
    runs = calculate_run_month_alerts(
        region_phases,
        first_season_month=OCTOBER,
        season_month_count=SEASON_MONTH_COUNT,
        months_until_season_start=1,
        report_lag_months=1,
    )

    # Assert
    assert runs.empty


def test_rank_is_the_share_of_other_values_below_with_ties_counting_half() -> None:
    # Arrange
    values = np.array([0.1, 0.4, 0.4, np.nan])

    # Act
    ranks = calculate_rank_among_others(values)

    # Assert
    assert ranks[:3] == pytest.approx([0, 0.75, 0.75])
    assert np.isnan(ranks[3])


def test_projections_are_scored_against_assuming_no_change() -> None:
    # Arrange
    pairs = pd.DataFrame(
        {
            "projected_share": [0.5, 0.2, 0.3],
            "current_share": [0.3, 0.3, 0.3],
            "later_share": [0.6, 0.4, 0.3],
        }
    )

    # Act
    scores = score_projections(pairs)

    # Assert
    assert scores["pair_count"] == 3
    assert scores["mean_absolute_error"] == pytest.approx(0.1)
    assert scores["mean_absolute_error_of_no_change"] == pytest.approx(0.133)
    # The first projected change is in the right direction, the second is not, and the
    # third projects no change.
    assert scores["projected_change_count"] == 2
    assert scores["share_of_changes_in_the_right_direction"] == pytest.approx(0.5)
