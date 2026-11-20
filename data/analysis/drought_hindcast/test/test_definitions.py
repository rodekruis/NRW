from itertools import combinations

from analysis.drought_hindcast.definitions import POOLED_REGION_SEASONS


def test_pooled_region_seasons_count_each_month_of_a_region_once() -> None:
    # Arrange
    pairs_in_the_same_region = [
        (first, second)
        for first, second in combinations(POOLED_REGION_SEASONS, 2)
        if first.region_key == second.region_key
    ]

    # Act
    shared_months = [
        set(first.months) & set(second.months)
        for first, second in pairs_in_the_same_region
    ]

    # Assert
    assert pairs_in_the_same_region
    assert not any(shared_months)
