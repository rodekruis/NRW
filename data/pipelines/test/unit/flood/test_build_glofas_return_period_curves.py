from __future__ import annotations

import numpy as np
import pytest
import xarray as xr
from data_management.seed_data_management.flood.build_glofas_return_period_curves import (
    clip_to_bounds,
    LATITUDE,
    LOCATION,
    LONGITUDE,
    SCALE,
    UPSTREAM_AREA,
)

_CELL_SIZE = 0.05


def _make_global_curves() -> xr.Dataset:
    """4 x 4 cells between 35.0 and 35.2 east and 16.0 and 16.2 south; coordinates are cell centres, north first."""
    latitudes = -16.0 - _CELL_SIZE / 2 - _CELL_SIZE * np.arange(4)
    longitudes = 35.0 + _CELL_SIZE / 2 + _CELL_SIZE * np.arange(4)
    cell_numbers = np.arange(16, dtype=np.float64).reshape(4, 4)
    return xr.Dataset(
        {
            LOCATION: ([LATITUDE, LONGITUDE], cell_numbers),
            SCALE: ([LATITUDE, LONGITUDE], cell_numbers / 10),
            UPSTREAM_AREA: ([LATITUDE, LONGITUDE], cell_numbers * 1e9),
        },
        coords={LATITUDE: latitudes, LONGITUDE: longitudes},
    )


def test_clip_to_bounds_keeps_the_cells_with_their_centre_inside():
    # Arrange: bounds around the four cells in the middle
    bounds = (35.06, -16.14, 35.14, -16.06)

    # Act
    curves = clip_to_bounds(_make_global_curves(), bounds, padding_degrees=0.0)

    # Assert
    np.testing.assert_array_equal(curves.location, [[5.0, 6.0], [9.0, 10.0]])
    np.testing.assert_array_equal(curves.scale, [[0.5, 0.6], [0.9, 1.0]])
    np.testing.assert_array_equal(curves.upstream_area, [[5e9, 6e9], [9e9, 10e9]])
    assert curves.transform.a == pytest.approx(_CELL_SIZE)
    assert curves.transform.e == pytest.approx(-_CELL_SIZE)
    assert curves.transform.c == pytest.approx(35.05)
    assert curves.transform.f == pytest.approx(-16.05)


def test_clip_to_bounds_pads_the_bounds():
    # Arrange
    bounds = (35.06, -16.14, 35.14, -16.06)

    # Act
    curves = clip_to_bounds(_make_global_curves(), bounds, padding_degrees=_CELL_SIZE)

    # Assert
    assert curves.location.shape == (4, 4)
    assert curves.transform.c == pytest.approx(35.0)
    assert curves.transform.f == pytest.approx(-16.0)


def test_clip_to_bounds_rejects_bounds_without_cells():
    # Arrange
    bounds = (10.0, 10.0, 11.0, 11.0)

    # Act / Assert
    with pytest.raises(ValueError, match="No GloFAS cells"):
        clip_to_bounds(_make_global_curves(), bounds, padding_degrees=0.0)
