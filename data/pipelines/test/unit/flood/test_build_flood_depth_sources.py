from pathlib import Path

import numpy as np
import pytest
import rasterio
from data_management.seed_data_management.flood.build_flood_depth_sources import (
    load_permanent_water,
    mask_permanent_water_fill,
    NODATA,
    PERMANENT_WATER_FILL_DEPTH_METRES,
    Tile,
)
from rasterio.transform import from_origin
from shapely.geometry import box

_PERMANENT_WATER_NODATA = 255


def _grid_profile(left: float = 0.0, top: float = 2.0) -> dict:
    return {"crs": "EPSG:4326", "transform": from_origin(left, top, 1, 1)}


def _write_permanent_water_tile(
    cache_directory: Path, tile: Tile, values: list[list[int]]
) -> None:
    """Write a tile of 1 degree pixels where load_permanent_water expects its cached download."""
    path = (
        cache_directory
        / "Permanent_WaterBodies"
        / f"{tile.filename_prefix}_permanent_water.tif"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    left, _, _, top = tile.geometry.bounds
    data = np.array(values, dtype=np.uint8)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=data.shape[0],
        width=data.shape[1],
        count=1,
        dtype=rasterio.uint8,
        crs="EPSG:4326",
        transform=from_origin(left, top, 1, 1),
        nodata=_PERMANENT_WATER_NODATA,
    ) as destination:
        destination.write(data, 1)


def test_mask_permanent_water_fill_masks_only_the_fill_on_permanent_water():
    # Arrange
    fill = PERMANENT_WATER_FILL_DEPTH_METRES
    depth = np.array([[fill, fill, 0.5], [2.0, NODATA, fill]], dtype=np.float32)
    is_permanent_water = np.array([[True, False, True], [True, True, True]])

    # Act
    mask_permanent_water_fill(
        depth, _grid_profile(), is_permanent_water, _grid_profile()
    )

    # Assert: the fill off permanent water and the modelled depths on it are kept
    expected = np.array([[NODATA, fill, 0.5], [2.0, NODATA, NODATA]], dtype=np.float32)
    np.testing.assert_array_equal(depth, expected)


def test_mask_permanent_water_fill_rejects_a_different_shape():
    # Arrange
    depth = np.zeros((2, 3), dtype=np.float32)
    is_permanent_water = np.zeros((2, 2), dtype=bool)

    # Act & Assert
    with pytest.raises(ValueError, match="not on the same grid"):
        mask_permanent_water_fill(
            depth, _grid_profile(), is_permanent_water, _grid_profile()
        )


def test_mask_permanent_water_fill_rejects_the_same_shape_on_a_shifted_grid():
    # Arrange: same shape, origin one pixel to the east
    depth = np.zeros((2, 3), dtype=np.float32)
    is_permanent_water = np.zeros((2, 3), dtype=bool)

    # Act & Assert
    with pytest.raises(ValueError, match="not on the same grid"):
        mask_permanent_water_fill(
            depth, _grid_profile(), is_permanent_water, _grid_profile(left=1.0)
        )


def test_load_permanent_water_merges_the_tiles_inside_the_bounds(tmp_path):
    # Arrange: two tiles of 2 x 2 pixels next to each other
    west_tile = Tile(identifier=1, name="WEST", geometry=box(0, 0, 2, 2))
    east_tile = Tile(identifier=2, name="EAST", geometry=box(2, 0, 4, 2))
    nodata = _PERMANENT_WATER_NODATA
    _write_permanent_water_tile(tmp_path, west_tile, [[1, nodata], [nodata, 1]])
    _write_permanent_water_tile(tmp_path, east_tile, [[nodata, 1], [1, 1]])

    # Act: bounds that leave out the westernmost column
    is_permanent_water, profile = load_permanent_water(
        [west_tile, east_tile], tmp_path, bounds=(1, 0, 4, 2)
    )

    # Assert
    expected = np.array([[False, False, True], [True, True, True]])
    np.testing.assert_array_equal(is_permanent_water, expected)
    assert profile["transform"] == from_origin(1, 2, 1, 1)
