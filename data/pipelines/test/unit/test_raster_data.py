import numpy as np
import pytest
from rasterio.transform import Affine, from_origin

from pipelines.constants import DEFAULT_CRS
from pipelines.infra.data_types.loaded_data_types import RasterData


def test_raises_for_a_transform_in_metres():
    # Arrange
    # Malawi in EPSG:3857, with cells of 1 km
    transform = from_origin(3636800, -1049300, 1000, 1000)

    # Act, Assert
    with pytest.raises(ValueError, match="outside the range of longitudes"):
        RasterData(
            array=np.zeros((2, 2), dtype=np.float32),
            transform=transform,
            crs=DEFAULT_CRS,
            nodata=0.0,
        )


def test_raises_when_only_some_corners_of_a_sheared_grid_are_outside_the_range():
    # Arrange
    # The centres of the first and of the last cell have longitude 0, the other two corners -398 and 398
    transform = Affine(2, -2, 0, 0, -0.01, 10)

    # Act, Assert
    with pytest.raises(ValueError, match="outside the range of longitudes"):
        RasterData(
            array=np.zeros((200, 200), dtype=np.float32),
            transform=transform,
            crs=DEFAULT_CRS,
            nodata=0.0,
        )


def test_accepts_a_global_grid_with_cell_centres_at_the_limits_of_the_range():
    # Arrange
    # Cell centres from -180 to 180 and from 90 to -90: the cell edges are half a cell out of the range
    cell_size = 0.25
    transform = from_origin(
        -180 - cell_size / 2, 90 + cell_size / 2, cell_size, cell_size
    )

    # Act
    raster = RasterData(
        array=np.zeros((721, 1441), dtype=np.float32),
        transform=transform,
        crs=DEFAULT_CRS,
        nodata=0.0,
    )

    # Assert
    assert raster.transform == transform
