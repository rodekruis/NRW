from pathlib import Path

import numpy as np
import pytest
import xarray as xr

from pipelines.infra.utils.raster import slice_netcdf_to_bounds


def test_raises_when_the_grid_has_no_cells_in_the_bounds(tmp_path: Path):
    # Arrange
    # A grid in metres (Malawi in EPSG:3857) has no cells in bounds in degrees
    input_path = tmp_path / "discharge.nc"
    xr.Dataset(
        {"dis": (("lat", "lon"), np.ones((2, 2), dtype=np.float32))},
        coords={"lat": [-1049300.0, -1938000.0], "lon": [3636800.0, 3998600.0]},
    ).to_netcdf(input_path)
    malawi_bounds = (32.67, -17.13, 35.92, -9.37)

    # Act, Assert
    with pytest.raises(ValueError, match="has no cells in bounds"):
        slice_netcdf_to_bounds(str(input_path), malawi_bounds)
