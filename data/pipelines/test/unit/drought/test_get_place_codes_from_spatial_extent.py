from pipelines.infra.data_types.admin_area_types import (
    AdminArea,
    AdminAreaProperties,
    AdminAreasSet,
)
from pipelines.infra.data_types.loaded_data_types import AlertConfig
from pipelines.infra.utils.exposure import get_place_codes_for_alert_config
from shapely.geometry import box


def _make_admin_areas() -> AdminAreasSet:
    return AdminAreasSet(
        admin_areas={
            "ET00": AdminArea(
                properties=AdminAreaProperties(
                    pcode="ET00",
                    name="Ethiopia",
                    admin_level=0,
                    country_code="ETH",
                ),
                geometry_type="MultiPolygon",
                coordinates=[],
            ),
            "ET01": AdminArea(
                properties=AdminAreaProperties(
                    pcode="ET01",
                    name="Oromia",
                    admin_level=1,
                    country_code="ETH",
                    parent_pcodes={0: "ET00"},
                ),
                geometry_type="MultiPolygon",
                coordinates=[],
            ),
            "ET0101": AdminArea(
                properties=AdminAreaProperties(
                    pcode="ET0101",
                    name="West Shewa",
                    admin_level=2,
                    country_code="ETH",
                    parent_pcodes={0: "ET00", 1: "ET01"},
                ),
                geometry_type="MultiPolygon",
                coordinates=[],
            ),
            "ET0102": AdminArea(
                properties=AdminAreaProperties(
                    pcode="ET0102",
                    name="East Shewa",
                    admin_level=2,
                    country_code="ETH",
                    parent_pcodes={0: "ET00", 1: "ET01"},
                ),
                geometry_type="MultiPolygon",
                coordinates=[],
            ),
        }
    )


def test_expands_to_all_admin_areas_at_target_level_without_a_geometry():
    config = AlertConfig(
        spatial_extent_name="National",
        temporal_extents=[],
    )
    result = get_place_codes_for_alert_config(config, _make_admin_areas(), 2)
    assert sorted(result) == ["ET0101", "ET0102"]


def test_expands_to_different_admin_level():
    config = AlertConfig(
        spatial_extent_name="National",
        temporal_extents=[],
    )
    result = get_place_codes_for_alert_config(config, _make_admin_areas(), 1)
    assert result == ["ET01"]


def test_returns_empty_when_no_areas_match_level():
    config = AlertConfig(
        spatial_extent_name="National",
        temporal_extents=[],
    )
    result = get_place_codes_for_alert_config(config, _make_admin_areas(), 3)
    assert result == []


def _make_square_admin_area(
    place_code: str, admin_level: int, left: float, width: float
) -> AdminArea:
    return AdminArea(
        properties=AdminAreaProperties(
            pcode=place_code,
            name=place_code,
            admin_level=admin_level,
            country_code="ETH",
        ),
        geometry_type="Polygon",
        coordinates=[
            [
                [left, 0.0],
                [left, 1.0],
                [left + width, 1.0],
                [left + width, 0.0],
                [left, 0.0],
            ]
        ],
    )


def test_derives_place_codes_at_target_level_from_the_geometry():
    # Arrange
    admin_areas = AdminAreasSet(
        admin_areas={
            "ET01": _make_square_admin_area("ET01", 1, 0.0, 3.0),
            "ET0101": _make_square_admin_area("ET0101", 2, 0.0, 1.0),
            "ET0102": _make_square_admin_area("ET0102", 2, 1.0, 1.0),
            "ET0103": _make_square_admin_area("ET0103", 2, 2.0, 1.0),
        }
    )
    config = AlertConfig(
        spatial_extent_name="Belg",
        temporal_extents=[],
        spatial_extent_geometry=box(0.0, 0.0, 2.0, 1.0),
    )

    # Act
    result = get_place_codes_for_alert_config(config, admin_areas, 2)

    # Assert
    assert result == ["ET0101", "ET0102"]
