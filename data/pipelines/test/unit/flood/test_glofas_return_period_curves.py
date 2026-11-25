from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pipelines.constants import DEFAULT_CRS
from pipelines.flood.constants import GLOFAS_VERSION
from pipelines.infra.data_types.glofas_return_period_curves import (
    get_glofas_return_period_curves_filename,
    GlofasReturnPeriodCurves,
)
from rasterio.transform import from_origin

_CELL_SIZE = 0.05


def _make_curves() -> GlofasReturnPeriodCurves:
    """2 x 3 cells with their north-west corner at (35.0, -16.0); the south-east cell has no curve."""
    return GlofasReturnPeriodCurves(
        location=np.array([[1.0, 2.0, 3.0], [4.0, 5.0, np.nan]]),
        scale=np.array([[0.1, 0.2, 0.3], [0.4, 0.5, np.nan]]),
        upstream_area=np.array([[1e9, 2e9, 3e9], [4e9, 5e9, np.nan]]),
        transform=from_origin(35.0, -16.0, _CELL_SIZE, _CELL_SIZE),
        crs=DEFAULT_CRS,
    )


def _write_curves(directory: Path) -> Path:
    path = directory / get_glofas_return_period_curves_filename("MWI", GLOFAS_VERSION)
    _make_curves().write_geotiff(path)
    return path


def test_curves_survive_a_round_trip_through_geotiff(tmp_path: Path):
    # Arrange
    curves = _make_curves()
    path = _write_curves(tmp_path)

    # Act
    loaded = GlofasReturnPeriodCurves.from_geotiff(path.read_bytes())

    # Assert
    np.testing.assert_array_equal(loaded.location, curves.location)
    np.testing.assert_array_equal(loaded.scale, curves.scale)
    np.testing.assert_array_equal(loaded.upstream_area, curves.upstream_area)
    assert loaded.transform == curves.transform
    assert loaded.crs == DEFAULT_CRS


def test_aligned_to_shifts_the_curves_onto_an_overlapping_grid():
    # Arrange: a grid of 2 x 2 cells that starts one cell east and one cell south of the curves
    curves = _make_curves()
    grid_transform = from_origin(
        35.0 + _CELL_SIZE, -16.0 - _CELL_SIZE, _CELL_SIZE, _CELL_SIZE
    )

    # Act
    aligned = curves.aligned_to(grid_transform, (2, 2))

    # Assert: only the north-west cell of the grid lies on a cell with a curve
    np.testing.assert_array_equal(aligned.location, [[5.0, np.nan], [np.nan, np.nan]])
    np.testing.assert_array_equal(aligned.scale, [[0.5, np.nan], [np.nan, np.nan]])
    assert aligned.transform == grid_transform


def test_aligned_to_tolerates_floating_point_noise_in_the_grid():
    # Arrange: the transform that rasterio derives from the coordinates of a forecast file
    curves = _make_curves()
    grid_transform = from_origin(
        35.0 - 1.6e-14, -16.0, 0.050000000000000266, _CELL_SIZE
    )

    # Act
    aligned = curves.aligned_to(grid_transform, (2, 3))

    # Assert
    np.testing.assert_array_equal(aligned.location, curves.location)


@pytest.mark.parametrize(
    "grid_transform",
    [
        from_origin(35.0 + _CELL_SIZE / 2, -16.0, _CELL_SIZE, _CELL_SIZE),
        from_origin(35.0, -16.0 + _CELL_SIZE / 2, _CELL_SIZE, _CELL_SIZE),
        from_origin(35.0, -16.0, 2 * _CELL_SIZE, 2 * _CELL_SIZE),
    ],
)
def test_aligned_to_rejects_a_grid_whose_cells_do_not_line_up(grid_transform):
    # Arrange
    curves = _make_curves()

    # Act / Assert
    with pytest.raises(ValueError, match="does not line up"):
        curves.aligned_to(grid_transform, (2, 3))
