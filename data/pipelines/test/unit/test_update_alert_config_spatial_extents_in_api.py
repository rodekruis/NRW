from data_management.api_data_management.update_alert_config_spatial_extents_in_api import (
    AlertConfigUpdate,
    plan_updates,
)

POLYGON = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
}
OTHER_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[0, 0], [2, 0], [2, 2], [0, 2], [0, 0]]],
}


def create_alert_config(alert_config_id: int, name: str, geometry: dict | None) -> dict:
    return {
        "id": alert_config_id,
        "hazardType": "floods",
        "countryCodeIso3": "MWI",
        "spatialExtentName": name,
        "spatialExtentGeometry": geometry,
    }


def test_plan_updates_only_the_alert_configs_whose_geometry_changes():
    # Arrange
    alert_configs = [
        create_alert_config(1, "G1", None),
        create_alert_config(2, "G2", POLYGON),
        create_alert_config(3, "G3", OTHER_POLYGON),
        create_alert_config(4, "G4", None),
    ]
    geometries = {
        ("floods", "MWI", "G1"): POLYGON,
        ("floods", "MWI", "G2"): POLYGON,
        ("floods", "MWI", "G3"): POLYGON,
    }

    # Act
    updates, unchanged_count, without_geometry = plan_updates(alert_configs, geometries)

    # Assert
    assert updates == [
        AlertConfigUpdate(1, ("floods", "MWI", "G1"), POLYGON),
        AlertConfigUpdate(3, ("floods", "MWI", "G3"), POLYGON),
    ]
    assert unchanged_count == 1
    assert without_geometry == [("floods", "MWI", "G4")]
