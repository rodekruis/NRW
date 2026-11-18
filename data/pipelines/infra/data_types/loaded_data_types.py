from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from pipelines.infra.data_types.data_config_types import DataSource
from rasterio.transform import Affine, xy
from shared.crs_helpers import is_in_longitude_latitude_range, validate_crs


@dataclass
class AlertConfig:
    spatial_extent_name: str
    spatial_extent_place_codes: list[str]
    temporal_extents: list[dict[str, list]]

    @staticmethod
    def from_api(raw: dict) -> AlertConfig:
        return AlertConfig(
            spatial_extent_name=str(raw["spatialExtentName"]),
            spatial_extent_place_codes=[
                str(p) for p in raw.get("spatialExtentPlaceCodes", [])
            ],
            temporal_extents=raw.get("temporalExtents", []),
        )


class DataType(StrEnum):
    """
    Enum of the different types of data that can be loaded.
    This is set during data loading.
    See the readme for more details.
    """

    # In-memory raster data (array + geo metadata)
    RASTER_DATA = "raster_data"

    # A FloodDepthProvider that lazily fetches flood depth rasters on demand
    FLOOD_DEPTH_PROVIDER = "flood_depth_provider"

    # an AdminAreasSet object
    ADMIN_AREA_SET = "admin_area_set"

    ALERT_CONFIG_LIST = "alert_config_list"

    # a dict of LocationPoints keyed by id
    LOCATION_POINT_DICT = "location_point_dict"

    # Generic types
    PATH_LIST = "path_list"

    # Default value until the type is set by the loader
    UNSPECIFIED = "unspecified"


@dataclass
class RasterData:
    """
    A raster in DEFAULT_CRS. Geometries in DEFAULT_CRS can thus be used with the
    transform without a check of the CRS.
    """

    array: np.ndarray
    transform: Affine
    crs: str  # the CRS that the source gives for the raster
    nodata: float  # sentinel for missing cells; sign/magnitude varies by source

    def __post_init__(self) -> None:
        validate_crs(self.crs, "Raster")

        # Finds a transform in a different CRS (e.g. metres) that has the label DEFAULT_CRS.
        # The centres of the four corner cells are used, not the cell edges: the outer
        # cells of a global grid extend half a cell out of the range.
        rows, columns = self.array.shape
        longitudes, latitudes = xy(
            self.transform,
            [0, 0, rows - 1, rows - 1],
            [0, columns - 1, 0, columns - 1],
        )
        cell_centre_bounds = (
            float(min(longitudes)),
            float(min(latitudes)),
            float(max(longitudes)),
            float(max(latitudes)),
        )
        if not is_in_longitude_latitude_range(cell_centre_bounds):
            raise ValueError(
                f"Raster cell centres {cell_centre_bounds} are outside the range of "
                f"longitudes and latitudes: the transform is not in {self.crs}"
            )


@dataclass
class LoadedDataSource:
    """
    The main container for data loaded.
    These are provided to the hazard logic pipeline code.
    """

    data_type: DataType
    data_source: DataSource
    data: object | None = None
    error: str | None = None
