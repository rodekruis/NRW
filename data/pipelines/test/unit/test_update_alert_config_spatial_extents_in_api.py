from data_management.api_data_management.update_alert_config_spatial_extents_in_api import (
    AlertConfigUpdate,
    plan_creations,
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


FLOOD_SETTINGS = {
    "temporalExtents": [{"lead-time-spectrum": ["0-day", "1-day"]}],
    "severityClassLevels": [{"label": "high", "threshold": 0.5}],
    "probabilityClassLevels": [{"label": "high", "threshold": 0.8}],
    "triggerAlertClass": "high",
    "triggerLeadTimeDuration": "P3D",
}


def create_alert_config(
    alert_config_id: int,
    name: str,
    geometry: dict | None,
    country: str = "MWI",
    settings: dict = FLOOD_SETTINGS,
) -> dict:
    return {
        "id": alert_config_id,
        "hazardType": "floods",
        "countryCodeIso3": country,
        "spatialExtentName": name,
        "spatialExtentGeometry": geometry,
        **settings,
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


def test_plan_creations_copies_the_flood_settings_of_the_country():
    # Arrange
    alert_configs = [
        create_alert_config(1, "G1", POLYGON),
        create_alert_config(2, "G2", None),
    ]
    geometries = {
        ("floods", "MWI", "G1"): POLYGON,
        ("floods", "MWI", "G3"): OTHER_POLYGON,
    }

    # Act
    creations, not_created = plan_creations(alert_configs, geometries)

    # Assert
    assert creations == [
        {
            "countryCodeIso3": "MWI",
            "hazardType": "floods",
            "spatialExtentName": "G3",
            "spatialExtentGeometry": OTHER_POLYGON,
            **FLOOD_SETTINGS,
        }
    ]
    assert not_created == []


def test_plan_creations_skips_a_country_without_one_set_of_flood_settings():
    # Arrange
    alert_configs = [
        create_alert_config(1, "G1", POLYGON, country="ZMB"),
        create_alert_config(
            2,
            "G2",
            POLYGON,
            country="ZMB",
            settings={**FLOOD_SETTINGS, "triggerAlertClass": "medium"},
        ),
    ]
    geometries = {
        ("floods", "ZMB", "G3"): POLYGON,
        ("floods", "PHL", "G4"): POLYGON,
        ("drought", "ETH", "Belg"): POLYGON,
    }

    # Act
    creations, not_created = plan_creations(alert_configs, geometries)

    # Assert
    assert creations == []
    assert [key for key, _ in not_created] == [
        ("drought", "ETH", "Belg"),
        ("floods", "PHL", "G4"),
        ("floods", "ZMB", "G3"),
    ]
