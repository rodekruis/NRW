from __future__ import annotations

import numpy as np
from pipelines.constants import DEFAULT_CRS, POPULATION_NODATA_VALUE
from pipelines.flood.determine_exposure import (
    clip_flood_depth_to_admin_areas,
    determine_spatial_extent,
    has_flooded_cells,
)
from pipelines.flood.forecast import validate_alert_config_place_codes
from pipelines.infra.data_types.admin_area_types import (
    AdminArea,
    AdminAreaProperties,
    AdminAreasSet,
)
from pipelines.infra.data_types.loaded_data_types import AlertConfig, RasterData
from pipelines.infra.data_types.location_point import LocationPoint
from pipelines.infra.utils.exposure import (
    aggregate_population_exposed,
    compute_population_exposed,
)
from rasterio.transform import from_origin
from shapely.geometry import box


def _build_admin_areas() -> AdminAreasSet:
    return AdminAreasSet(
        admin_areas={
            "PC001": AdminArea(
                properties=AdminAreaProperties(
                    pcode="PC001",
                    name="Test Area",
                    admin_level=1,
                    country_code="PC",
                ),
                geometry_type="Polygon",
                coordinates=[
                    [
                        [0.0, 0.0],
                        [0.0, 2.0],
                        [2.0, 2.0],
                        [2.0, 0.0],
                        [0.0, 0.0],
                    ]
                ],
            )
        },
    )


def _build_partial_admin_areas() -> AdminAreasSet:
    return AdminAreasSet(
        admin_areas={
            "PC001": AdminArea(
                properties=AdminAreaProperties(
                    pcode="PC001",
                    name="Partial Test Area",
                    admin_level=1,
                    country_code="PC",
                ),
                geometry_type="Polygon",
                coordinates=[
                    [
                        [0.0, 1.0],
                        [0.0, 2.0],
                        [1.0, 2.0],
                        [1.0, 1.0],
                        [0.0, 1.0],
                    ]
                ],
            )
        },
    )


def test_validate_alert_config_place_codes_accepts_known_place_codes():
    # Arrange
    alert_configs = [
        AlertConfig(
            spatial_extent_name="station-1",
            spatial_extent_place_codes=["PC001"],
            temporal_extents=[],
        )
    ]

    # Act
    errors = validate_alert_config_place_codes(
        alert_configs,
        _build_admin_areas(),
        "TST",
    )

    # Assert
    assert errors == []


def test_validate_alert_config_place_codes_rejects_unknown_place_codes():
    # Arrange
    alert_configs = [
        AlertConfig(
            spatial_extent_name="station-1",
            spatial_extent_place_codes=["PC001", "PC002", "PC003"],
            temporal_extents=[],
        )
    ]

    # Act
    errors = validate_alert_config_place_codes(
        alert_configs,
        _build_admin_areas(),
        "TST",
    )

    # Assert
    assert errors == [
        "TST flood alert config 'station-1' references 2 place code(s) not present in target admin areas: PC002, PC003"
    ]


def test_compute_population_exposed_sums_only_flooded_pixels():
    population_data = RasterData(
        array=np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32),
        transform=from_origin(0, 2, 1, 1),
        crs=DEFAULT_CRS,
        nodata=-9999.0,
    )
    flood_depth_data = RasterData(
        array=np.array([[0, 5], [2, 0]], dtype=np.float32),
        transform=from_origin(0, 2, 1, 1),
        crs=DEFAULT_CRS,
        nodata=POPULATION_NODATA_VALUE,
    )

    population_exposed_raster = compute_population_exposed(
        population_raster=population_data,
        hazard_spatial_extent_raster=flood_depth_data,
    )
    assert population_exposed_raster is not None

    population = aggregate_population_exposed(
        population_exposed_raster=population_exposed_raster,
        place_codes_exposed=["PC001"],
        admin_areas=_build_admin_areas(),
    )

    assert population == {"PC001": 50.0}


def test_compute_population_exposed_returns_zero_for_empty_spatial_extent():
    population_data = RasterData(
        array=np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32),
        transform=from_origin(0, 2, 1, 1),
        crs=DEFAULT_CRS,
        nodata=-9999.0,
    )
    flood_depth_data = RasterData(
        array=np.zeros((2, 2), dtype=np.float32),
        transform=from_origin(0, 2, 1, 1),
        crs=DEFAULT_CRS,
        nodata=POPULATION_NODATA_VALUE,
    )

    population_exposed_raster = compute_population_exposed(
        population_raster=population_data,
        hazard_spatial_extent_raster=flood_depth_data,
    )
    assert population_exposed_raster is not None

    population = aggregate_population_exposed(
        population_exposed_raster=population_exposed_raster,
        place_codes_exposed=["PC001"],
        admin_areas=_build_admin_areas(),
    )

    assert population == {}


def test_aggregate_population_exposed_keeps_flooded_area_without_population():
    # Arrange
    population_data = RasterData(
        array=np.array([[0.0, 0.0], [30.0, 40.0]], dtype=np.float32),
        transform=from_origin(0, 2, 1, 1),
        crs=DEFAULT_CRS,
        nodata=POPULATION_NODATA_VALUE,
    )
    flood_depth_data = RasterData(
        array=np.array([[5, 5], [0, 0]], dtype=np.float32),
        transform=from_origin(0, 2, 1, 1),
        crs=DEFAULT_CRS,
        nodata=POPULATION_NODATA_VALUE,
    )
    population_exposed_raster = compute_population_exposed(
        population_raster=population_data,
        hazard_spatial_extent_raster=flood_depth_data,
    )
    assert population_exposed_raster is not None

    # Act
    population = aggregate_population_exposed(
        population_exposed_raster=population_exposed_raster,
        place_codes_exposed=["PC001"],
        admin_areas=_build_admin_areas(),
    )

    # Assert
    assert population == {"PC001": 0.0}


def test_clip_flood_depth_to_admin_areas_clips_to_geometry():
    flood_depth_data = RasterData(
        array=np.array([[1, 2], [3, 4]], dtype=np.float32),
        transform=from_origin(0, 2, 1, 1),
        crs=DEFAULT_CRS,
        nodata=POPULATION_NODATA_VALUE,
    )

    clipped = clip_flood_depth_to_admin_areas(
        place_codes=["PC001"],
        admin_areas=_build_partial_admin_areas(),
        flood_depth_raster=flood_depth_data,
        station_code="station_001",
    )

    assert clipped.array.shape == (1, 1)
    assert clipped.array[0, 0] == 1.0


def _build_station(station_id: str = "station_001") -> LocationPoint:
    return LocationPoint(name="Test Station", lat=1.0, lon=1.0, id=station_id)


def test_determine_spatial_extent_filters_to_valid_place_codes():
    flood_depth_data = RasterData(
        array=np.array([[1, 2], [3, 4]], dtype=np.float32),
        transform=from_origin(0, 2, 1, 1),
        crs=DEFAULT_CRS,
        nodata=POPULATION_NODATA_VALUE,
    )

    admin_areas = _build_admin_areas()

    clipped, valid_codes = determine_spatial_extent(
        station=_build_station(),
        station_place_codes=["PC001", "INVALID_CODE"],
        admin_areas=admin_areas,
        flood_depth_raster=flood_depth_data,
    )

    assert valid_codes == ["PC001"]
    assert clipped is not None


def test_determine_spatial_extent_returns_early_when_all_place_codes_invalid():
    flood_depth_data = RasterData(
        array=np.array([[1, 2], [3, 4]], dtype=np.float32),
        transform=from_origin(0, 2, 1, 1),
        crs=DEFAULT_CRS,
        nodata=POPULATION_NODATA_VALUE,
    )

    admin_areas = _build_admin_areas()

    clipped, valid_codes = determine_spatial_extent(
        station=_build_station(),
        station_place_codes=["INVALID_1", "INVALID_2"],
        admin_areas=admin_areas,
        flood_depth_raster=flood_depth_data,
    )

    assert valid_codes == []
    assert clipped is None


def test_has_flooded_cells_is_true_for_positive_flood_depth():
    # Arrange
    flood_depth_data = RasterData(
        array=np.array([[-9999.0, 0.0], [0.0, 0.4]], dtype=np.float32),
        transform=from_origin(0, 2, 1, 1),
        crs=DEFAULT_CRS,
        nodata=-9999.0,
    )

    # Act
    result = has_flooded_cells(flood_depth_data)

    # Assert
    assert result is True


def test_has_flooded_cells_is_false_without_positive_flood_depth():
    # Arrange
    flood_depth_data = RasterData(
        array=np.array([[-9999.0, 0.0], [0.0, -9999.0]], dtype=np.float32),
        transform=from_origin(0, 2, 1, 1),
        crs=DEFAULT_CRS,
        nodata=-9999.0,
    )

    # Act
    result = has_flooded_cells(flood_depth_data)

    # Assert
    assert result is False


def test_determine_spatial_extent_returns_early_when_place_codes_empty():
    flood_depth_data = RasterData(
        array=np.array([[1, 2], [3, 4]], dtype=np.float32),
        transform=from_origin(0, 2, 1, 1),
        crs=DEFAULT_CRS,
        nodata=POPULATION_NODATA_VALUE,
    )

    admin_areas = _build_admin_areas()

    clipped, valid_codes = determine_spatial_extent(
        station=_build_station(),
        station_place_codes=[],
        admin_areas=admin_areas,
        flood_depth_raster=flood_depth_data,
    )

    assert valid_codes == []
    assert clipped is None


def _build_two_admin_areas() -> AdminAreasSet:
    """Two admin areas side by side: PC001 from x=0 to 1, PC002 from x=1 to 2."""
    return AdminAreasSet(
        admin_areas={
            place_code: AdminArea(
                properties=AdminAreaProperties(
                    pcode=place_code,
                    name=place_code,
                    admin_level=1,
                    country_code="PC",
                ),
                geometry_type="Polygon",
                coordinates=[
                    [
                        [left, 0.0],
                        [left, 2.0],
                        [left + 1.0, 2.0],
                        [left + 1.0, 0.0],
                        [left, 0.0],
                    ]
                ],
            )
            for place_code, left in (("PC001", 0.0), ("PC002", 1.0))
        },
    )


def _build_flood_depth_two_by_two() -> RasterData:
    return RasterData(
        array=np.array([[1, 2], [3, 4]], dtype=np.float32),
        transform=from_origin(0, 2, 1, 1),
        crs=DEFAULT_CRS,
        nodata=POPULATION_NODATA_VALUE,
    )


def test_determine_spatial_extent_uses_the_geometry_instead_of_the_place_codes():
    # Arrange
    spatial_extent_geometry = box(0.0, 0.0, 1.0, 2.0)

    # Act
    clipped, place_codes = determine_spatial_extent(
        station=_build_station(),
        station_place_codes=["PC002"],
        admin_areas=_build_two_admin_areas(),
        flood_depth_raster=_build_flood_depth_two_by_two(),
        spatial_extent_geometry=spatial_extent_geometry,
    )

    # Assert
    assert place_codes == ["PC001"]
    assert clipped is not None
    assert clipped.array.tolist() == [[1.0], [3.0]]


def test_determine_spatial_extent_leaves_out_admin_areas_with_a_sliver_inside_the_geometry():
    # Arrange
    spatial_extent_geometry = box(0.0, 0.0, 1.001, 2.0)

    # Act
    _, place_codes = determine_spatial_extent(
        station=_build_station(),
        station_place_codes=[],
        admin_areas=_build_two_admin_areas(),
        flood_depth_raster=_build_flood_depth_two_by_two(),
        spatial_extent_geometry=spatial_extent_geometry,
    )

    # Assert
    assert place_codes == ["PC001"]


def test_determine_spatial_extent_returns_early_when_the_geometry_overlaps_no_admin_area():
    # Arrange
    spatial_extent_geometry = box(10.0, 10.0, 11.0, 11.0)

    # Act
    clipped, place_codes = determine_spatial_extent(
        station=_build_station(),
        station_place_codes=["PC001"],
        admin_areas=_build_two_admin_areas(),
        flood_depth_raster=_build_flood_depth_two_by_two(),
        spatial_extent_geometry=spatial_extent_geometry,
    )

    # Assert
    assert place_codes == []
    assert clipped is None


def test_alert_config_from_api_reads_the_spatial_extent_geometry():
    # Arrange
    raw = {
        "spatialExtentName": "station-1",
        "spatialExtentPlaceCodes": ["PC001"],
        "temporalExtents": [],
        "spatialExtentGeometry": {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
        },
    }

    # Act
    config = AlertConfig.from_api(raw)

    # Assert
    assert config.spatial_extent_geometry is not None
    assert config.spatial_extent_geometry.equals(box(0, 0, 1, 1))


def test_alert_config_from_api_without_spatial_extent_geometry_has_none():
    # Arrange
    raw = {
        "spatialExtentName": "station-1",
        "spatialExtentPlaceCodes": ["PC001"],
        "temporalExtents": [],
        "spatialExtentGeometry": None,
    }

    # Act
    config = AlertConfig.from_api(raw)

    # Assert
    assert config.spatial_extent_geometry is None
