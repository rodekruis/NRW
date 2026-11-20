import pandas as pd
from analysis.drought_hindcast.check_fews_net import IMPACT_COLUMN
from analysis.drought_hindcast.check_kenya_region import rank_seasons
from analysis.drought_hindcast.compare_outcomes import (
    get_events,
    Outcome,
    RAINFALL_COLUMN,
)


def test_a_season_counts_for_both_outcomes_only_when_dry_and_followed_by_impact() -> (
    None
):
    # Arrange
    cases = pd.DataFrame(
        {
            RAINFALL_COLUMN: [True, True, False, False],
            IMPACT_COLUMN: [True, False, True, False],
        }
    )

    # Act
    events = get_events(cases)

    # Assert
    assert events[Outcome.RAINFALL].tolist() == [True, True, False, False]
    assert events[Outcome.IMPACT].tolist() == [True, False, True, False]
    assert events[Outcome.RAINFALL_AND_IMPACT].tolist() == [True, False, False, False]


def test_seasons_are_ranked_from_the_driest_per_area_and_incomplete_years_left_out() -> (
    None
):
    # Arrange
    monthly_rainfall = pd.DataFrame(
        {
            "year": [2021, 2021, 2022, 2022, 2023, 2023, 2024],
            "month": [10, 11, 10, 11, 10, 11, 10],
            "national": [50.0, 50.0, 10.0, 20.0, 80.0, 90.0, 5.0],
            "arid": [30.0, 30.0, 40.0, 40.0, 5.0, 5.0, 1.0],
        }
    )

    # Act
    seasons = rank_seasons(monthly_rainfall, season_months=(10, 11)).set_index(
        "season_year"
    )

    # Assert
    assert seasons.index.tolist() == [2021, 2022, 2023]
    assert seasons["national_rainfall_mm"].tolist() == [100.0, 30.0, 170.0]
    assert seasons["national_rank_from_driest"].tolist() == [2, 1, 3]
    assert seasons["arid_rank_from_driest"].tolist() == [2, 3, 1]
    assert seasons["national_is_drought"].tolist() == [False, True, False]
