from __future__ import annotations

import numpy as np
import pytest
from pipelines.flood.footprint_method import (
    compute_return_period,
    interpolate_flood_depth,
    regrid_return_period,
    RegriddingMethod,
)
from rasterio.transform import from_origin

_MAXIMUM_RETURN_PERIOD = 500.0
_MINIMUM_RETURN_PERIOD = 1.5
# Two GloFAS cells of 1 degree next to each other, and a flood map of four 0.5-degree pixels across them.
_CELL_TRANSFORM = from_origin(0, 1, 1, 1)
_PIXEL_TRANSFORM = from_origin(0, 1, 0.5, 0.5)
_PIXEL_SHAPE = (2, 4)


def _gumbel_discharge(return_period: float, location: float, scale: float) -> float:
    return float(location - scale * np.log(-np.log(1 - 1 / return_period)))


def _flood_map_loader(
    depth_by_return_period: dict[int, float], loaded: list[int] | None = None
):
    def load_flood_map(return_period: int) -> np.ndarray:
        if loaded is not None:
            loaded.append(return_period)
        return np.full((1, 1), depth_by_return_period[return_period], dtype=np.float32)

    return load_flood_map


@pytest.mark.parametrize("return_period", [1.5, 2.0, 10.0, 100.0, 500.0])
def test_compute_return_period_inverts_the_gumbel_curve(return_period: float):
    # Arrange
    location, scale = 1869.0, 739.0
    discharge = _gumbel_discharge(return_period, location, scale)

    # Act
    result = compute_return_period(
        np.array([discharge]),
        np.array([location]),
        np.array([scale]),
        maximum_return_period=_MAXIMUM_RETURN_PERIOD,
    )

    # Assert
    assert result[0] == pytest.approx(return_period, rel=1e-9)


def test_compute_return_period_handles_edge_values():
    # Arrange
    discharge = np.array([0.0, 1e9, np.nan, 100.0, 100.0])
    location = np.array([1000.0, 1000.0, 1000.0, np.nan, 100.0])
    scale = np.array([10.0, 10.0, 10.0, 10.0, 0.0])

    # Act
    result = compute_return_period(
        discharge, location, scale, maximum_return_period=_MAXIMUM_RETURN_PERIOD
    )

    # Assert
    assert result[0] == 1.0
    assert result[1] == _MAXIMUM_RETURN_PERIOD
    assert np.isnan(result[2:]).all()


def test_regrid_nearest_gives_each_pixel_its_own_cell():
    # Arrange
    return_period = np.array([[2.0, 20.0]])

    # Act
    regridded = regrid_return_period(
        return_period,
        _CELL_TRANSFORM,
        _PIXEL_TRANSFORM,
        _PIXEL_SHAPE,
        RegriddingMethod.NEAREST,
    )

    # Assert
    np.testing.assert_array_equal(regridded, [[2, 2, 20, 20], [2, 2, 20, 20]])


def test_regrid_nearest_skips_cells_that_do_not_drive():
    # Arrange
    return_period = np.array([[np.nan, 20.0]])

    # Act
    regridded = regrid_return_period(
        return_period,
        _CELL_TRANSFORM,
        _PIXEL_TRANSFORM,
        _PIXEL_SHAPE,
        RegriddingMethod.NEAREST,
    )

    # Assert
    np.testing.assert_array_equal(regridded, np.full(_PIXEL_SHAPE, 20.0))


def test_regrid_bilinear_blends_between_cell_centres():
    # Arrange
    return_period = np.array([[2.0, 20.0]])

    # Act
    regridded = regrid_return_period(
        return_period,
        _CELL_TRANSFORM,
        _PIXEL_TRANSFORM,
        _PIXEL_SHAPE,
        RegriddingMethod.BILINEAR,
    )

    # Assert: pixel centres at 0.25, 0.75, 1.25 and 1.75 degrees, cell centres at 0.5 and 1.5
    np.testing.assert_allclose(regridded[0], [2.0, 6.5, 15.5, 20.0])
    np.testing.assert_allclose(regridded[1], regridded[0])


def test_regrid_bilinear_fills_cells_that_do_not_drive_before_blending():
    # Arrange
    return_period = np.array([[np.nan, 20.0]])

    # Act
    regridded = regrid_return_period(
        return_period,
        _CELL_TRANSFORM,
        _PIXEL_TRANSFORM,
        _PIXEL_SHAPE,
        RegriddingMethod.BILINEAR,
    )

    # Assert
    np.testing.assert_allclose(regridded, np.full(_PIXEL_SHAPE, 20.0))


@pytest.mark.parametrize("method", list(RegriddingMethod))
def test_regrid_leaves_pixels_outside_the_mask_empty(method: RegriddingMethod):
    # Arrange
    return_period = np.array([[2.0, 20.0]])
    mask = np.array([[True, False, False, True], [False, False, False, False]])

    # Act
    regridded = regrid_return_period(
        return_period,
        _CELL_TRANSFORM,
        _PIXEL_TRANSFORM,
        _PIXEL_SHAPE,
        method,
        target_mask=mask,
    )

    # Assert
    assert regridded[0, 0] == 2.0
    assert regridded[0, 3] == 20.0
    assert np.isnan(regridded[~mask]).all()


@pytest.mark.parametrize("method", list(RegriddingMethod))
def test_regrid_is_empty_when_no_cell_drives(method: RegriddingMethod):
    # Arrange
    return_period = np.full((1, 2), np.nan)

    # Act
    regridded = regrid_return_period(
        return_period, _CELL_TRANSFORM, _PIXEL_TRANSFORM, _PIXEL_SHAPE, method
    )

    # Assert
    assert np.isnan(regridded).all()


def test_regrid_rejects_a_south_up_grid():
    # Arrange
    south_up_transform = from_origin(0, 0, 1, -1)

    # Act / Assert
    with pytest.raises(ValueError, match="north-up"):
        regrid_return_period(
            np.array([[2.0, 20.0]]),
            south_up_transform,
            _PIXEL_TRANSFORM,
            _PIXEL_SHAPE,
            RegriddingMethod.NEAREST,
        )


@pytest.mark.parametrize(
    ("return_period", "expected_depth"),
    [
        (np.nan, 0.0),
        (1.2, 0.0),  # below the minimum return period
        (1.5, 0.5 / 9 * 0.9),  # linear scaling of the lowest map
        (5.5, 0.45),
        (10.0, 0.9),
        (15.0, 1.4),  # halfway between the 10- and 20-year maps
        (20.0, 1.9),
        (35.0, 2.4),
        (50.0, 2.9),
        (9999.0, 2.9),  # above the highest map
    ],
)
def test_interpolate_flood_depth(return_period: float, expected_depth: float):
    # Arrange
    load_flood_map = _flood_map_loader({10: 0.9, 20: 1.9, 50: 2.9})

    # Act
    depth = interpolate_flood_depth(
        np.array([[return_period]]),
        load_flood_map,
        available_return_periods=[10, 20, 50],
        minimum_return_period=_MINIMUM_RETURN_PERIOD,
    )

    # Assert
    assert depth[0, 0] == pytest.approx(expected_depth, abs=1e-6)


@pytest.mark.parametrize(
    ("return_period", "expected_maps"),
    [(1.2, []), (5.0, [10]), (15.0, [10, 20]), (30.0, [20, 50]), (9999.0, [20, 50])],
)
def test_interpolate_flood_depth_loads_only_the_maps_it_interpolates_between(
    return_period: float, expected_maps: list[int]
):
    # Arrange
    loaded: list[int] = []
    load_flood_map = _flood_map_loader({10: 0.9, 20: 1.9, 50: 2.9}, loaded)

    # Act
    interpolate_flood_depth(
        np.array([[return_period]]),
        load_flood_map,
        available_return_periods=[10, 20, 50],
        minimum_return_period=_MINIMUM_RETURN_PERIOD,
    )

    # Assert
    assert sorted(loaded) == expected_maps


def test_interpolate_flood_depth_starts_from_zero_where_the_lower_map_is_dry():
    # Arrange
    load_flood_map = _flood_map_loader({10: 0.0, 20: 1.0})

    # Act
    depth = interpolate_flood_depth(
        np.array([[12.5]]),
        load_flood_map,
        available_return_periods=[10, 20],
        minimum_return_period=_MINIMUM_RETURN_PERIOD,
    )

    # Assert
    assert depth[0, 0] == pytest.approx(0.25)


def test_interpolate_flood_depth_rejects_maps_at_the_zero_depth_return_period():
    # Arrange
    load_flood_map = _flood_map_loader({1: 0.5})

    # Act / Assert
    with pytest.raises(ValueError, match="return periods above"):
        interpolate_flood_depth(
            np.array([[2.0]]),
            load_flood_map,
            available_return_periods=[1],
            minimum_return_period=_MINIMUM_RETURN_PERIOD,
        )
