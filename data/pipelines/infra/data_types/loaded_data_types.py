from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import shapely
from pipelines.infra.data_types.data_config_types import DataSource
from rasterio.transform import Affine, xy
from shapely.geometry import MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid
from shared.crs_helpers import is_in_longitude_latitude_range, validate_crs


@dataclass
class AlertConfig:
    spatial_extent_name: str
    temporal_extents: list[dict[str, list]]
    # The area of the alert (GeoJSON Polygon or MultiPolygon); None means the whole country
    spatial_extent_geometry: BaseGeometry | None = None

    @staticmethod
    def from_api(raw: dict) -> AlertConfig:
        return AlertConfig(
            spatial_extent_name=str(raw["spatialExtentName"]),
            temporal_extents=raw.get("temporalExtents", []),
            spatial_extent_geometry=(
                _to_valid_area(shape(raw["spatialExtentGeometry"]))
                if raw.get("spatialExtentGeometry")
                else None
            ),
        )


def _to_valid_area(geometry: BaseGeometry) -> BaseGeometry | None:
    """Repair an invalid polygon (a self-intersection, a hole outside its shell), so that
    intersections with it cannot fail. The API rejects such polygons; this guards older data.
    A repair can leave lines or points behind, which are not part of an area."""
    if geometry.is_valid:
        return geometry
    polygons = [
        part
        for part in shapely.get_parts(make_valid(geometry))
        if isinstance(part, Polygon) and not part.is_empty
    ]
    if not polygons:
        return None
    return polygons[0] if len(polygons) == 1 else MultiPolygon(polygons)


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
