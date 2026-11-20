import numpy as np
import pytest
from analysis.drought_hindcast.region_weights import calculate_cell_weights
from analysis.drought_hindcast.study_area import Bounds
from shapely.geometry import box, mapping


def test_weights_are_share_of_cell_in_region_times_cosine_of_latitude() -> None:
    # Arrange
    bounds = Bounds(west=0, south=0, east=2, north=2)
    # Covers the whole north-west cell and the western half of the south-west cell.
    geometry = mapping(box(0, 0, 0.5, 1).union(box(0, 1, 1, 2)))

    # Act
    weights = calculate_cell_weights(
        geometry, bounds, cell_size_degrees=1, subcell_count=10
    )

    # Assert
    assert weights == pytest.approx(
        np.array(
            [
                [np.cos(np.deg2rad(1.5)), 0],
                [0.5 * np.cos(np.deg2rad(0.5)), 0],
            ]
        )
    )
