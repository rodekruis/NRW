import pytest
from analysis.drought_hindcast.definitions import RegionSeason
from analysis.drought_hindcast.plot_countries import (
    count_years_after_rainy_season_start,
    get_first_reliable_lead_time,
    group_by_country,
)

WHOLE_RAINY_SEASON = RegionSeason("ZWE", "National", "Oct-Mar", (10, 11, 12, 1, 2, 3))
FIRST_HALF = RegionSeason(
    "ZWE", "National", "OND", (10, 11, 12), is_in_pooled_results=False
)
SECOND_HALF = RegionSeason(
    "ZWE", "National", "JFM", (1, 2, 3), is_in_pooled_results=False
)


@pytest.mark.parametrize(
    ("region_season", "expected_year_count"),
    [(WHOLE_RAINY_SEASON, 0), (FIRST_HALF, 0), (SECOND_HALF, 1)],
)
def test_season_after_the_new_year_belongs_to_the_rainy_season_of_the_year_before(
    region_season: RegionSeason, expected_year_count: int
) -> None:
    # Arrange
    region_seasons = [WHOLE_RAINY_SEASON, FIRST_HALF, SECOND_HALF]

    # Act
    year_count = count_years_after_rainy_season_start(region_season, region_seasons)

    # Assert
    assert year_count == expected_year_count


def test_seasons_of_a_country_are_ordered_by_start_with_a_whole_season_before_its_halves() -> (
    None
):
    # Arrange
    long_rains = RegionSeason("KEN", "National", "MAM", (3, 4, 5))
    short_rains = RegionSeason("KEN", "National", "OND", (10, 11, 12))
    region_seasons = [
        SECOND_HALF,
        short_rains,
        FIRST_HALF,
        long_rains,
        WHOLE_RAINY_SEASON,
    ]

    # Act
    countries = group_by_country(region_seasons)

    # Assert
    assert countries == {
        "ZWE": [WHOLE_RAINY_SEASON, FIRST_HALF, SECOND_HALF],
        "KEN": [long_rains, short_rains],
    }


def test_season_of_another_region_is_not_taken_as_the_rainy_season() -> None:
    # Arrange
    season_of_another_region = RegionSeason("KEN", "National", "MAM", (3, 4, 5))

    # Act
    year_count = count_years_after_rainy_season_start(
        season_of_another_region, [WHOLE_RAINY_SEASON, season_of_another_region]
    )

    # Assert
    assert year_count == 0


@pytest.mark.parametrize(
    ("beats_chance_by_lead_time", "expected_lead_time"),
    [
        # From two months before onwards.
        ({4: False, 3: False, 2: True, 1: True, 0: True}, 2),
        # Four months before is taken as luck: three months before does not beat chance.
        ({4: True, 3: False, 2: False, 1: True, 0: True}, 1),
        ({4: True, 3: True, 2: True, 1: True, 0: True}, 4),
        # Not at the season start, so at no lead time.
        ({4: True, 3: True, 2: True, 1: True, 0: False}, None),
    ],
)
def test_reliable_lead_time_needs_every_later_forecast_to_beat_chance_too(
    beats_chance_by_lead_time: dict[int, bool], expected_lead_time: int | None
) -> None:
    # Act
    lead_time = get_first_reliable_lead_time(beats_chance_by_lead_time)

    # Assert
    assert lead_time == expected_lead_time
