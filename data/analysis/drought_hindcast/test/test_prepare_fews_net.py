import pandas as pd
import pytest
from analysis.drought_hindcast.prepare_fews_net import (
    calculate_region_phases,
    CRISIS_OR_WORSE_COLUMN,
    get_phase_share_column,
    select_unit_areas_in_region,
)
from shapely.geometry import box, mapping

REPORT = {
    "reporting_date": "2024-10-01",
    "scenario": "ML1",
    "projection_start": "2024-10-01",
    "projection_end": "2025-01-31",
    "source_document": "Food Security Outlook",
}


def test_units_are_selected_by_their_centre() -> None:
    # Arrange
    geographic_units = pd.DataFrame(
        {
            "fnid": ["inside", "outside"],
            "area_km2": [100.0, 300.0],
            "longitude": [0.5, 1.5],
            "latitude": [0.5, 0.5],
        }
    )
    region_geometry = mapping(box(0, 0, 1, 1))

    # Act
    area_by_unit = select_unit_areas_in_region(geographic_units, region_geometry)

    # Assert
    assert area_by_unit.to_dict() == {"inside": 100.0}


def test_phase_shares_are_weighted_by_the_area_of_the_units_in_the_region() -> None:
    # Arrange
    classifications = pd.DataFrame(
        [
            {**REPORT, "fnid": "small", "value": 2.0},
            {**REPORT, "fnid": "large", "value": 3.0},
            {**REPORT, "fnid": "larger", "value": 4.0},
            {**REPORT, "fnid": "other_region", "value": 4.0},
        ]
    )
    area_by_unit = pd.Series(
        {"small": 100.0, "large": 300.0, "larger": 600.0}, name="area_km2"
    )

    # Act
    region_phases = calculate_region_phases(classifications, area_by_unit)

    # Assert
    assert len(region_phases) == 1
    report = region_phases.iloc[0]
    assert report["unit_count"] == 3
    assert report["classified_area_km2"] == pytest.approx(1000)
    assert report[get_phase_share_column(1)] == 0
    assert report[get_phase_share_column(2)] == pytest.approx(0.1)
    assert report[get_phase_share_column(3)] == pytest.approx(0.3)
    assert report[CRISIS_OR_WORSE_COLUMN] == pytest.approx(0.9)


def test_a_report_keeps_one_row_when_a_unit_has_another_projection_period() -> None:
    # Arrange
    classifications = pd.DataFrame(
        [
            {**REPORT, "fnid": "first", "value": 1.0},
            {**REPORT, "fnid": "second", "value": 1.0},
            {**REPORT, "fnid": "third", "value": 3.0, "projection_end": "2024-12-31"},
        ]
    )
    area_by_unit = pd.Series(
        {"first": 100.0, "second": 100.0, "third": 200.0}, name="area_km2"
    )

    # Act
    region_phases = calculate_region_phases(classifications, area_by_unit)

    # Assert
    assert len(region_phases) == 1
    report = region_phases.iloc[0]
    assert report["projection_end"] == REPORT["projection_end"]
    assert report[CRISIS_OR_WORSE_COLUMN] == pytest.approx(0.5)
