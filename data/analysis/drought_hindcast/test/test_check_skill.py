import numpy as np
import pytest
from analysis.drought_hindcast.check_skill import calculate_measures


def test_measures_are_calculated_per_arrangement_of_the_years() -> None:
    # Arrange
    # Three years of one region-season: alerts in the first two, a drought in the first.
    is_alert = np.array([[1.0], [1.0], [0.0]])
    actual_droughts = np.array([[1.0], [0.0], [0.0]])
    droughts_moved_to_the_last_year = np.array([[0.0], [0.0], [1.0]])

    # Act
    measures = calculate_measures(
        is_alert, np.stack([actual_droughts, droughts_moved_to_the_last_year])
    )

    # Assert
    assert measures["hit_rate"].tolist() == [1, 0]
    assert measures["false_alarm_ratio"].tolist() == [pytest.approx(1 / 2), 1]


def test_measures_leave_out_seasons_that_are_not_scored() -> None:
    # Arrange
    # The second region-season has no observation yet in the last year.
    is_alert = np.array([[1.0, 1.0], [0.0, 1.0]])
    is_drought = np.array([[[1.0, 0.0], [1.0, np.nan]]])

    # Act
    measures = calculate_measures(is_alert, is_drought)

    # Assert
    assert measures["hit_rate"].tolist() == [pytest.approx(1 / 2)]
    assert measures["false_alarm_ratio"].tolist() == [pytest.approx(1 / 2)]
