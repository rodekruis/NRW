"""Summarise the FEWS NET classifications per region: the share of the area in each phase."""

import json

import pandas as pd
import shapely
from analysis.drought_hindcast.definitions import REGION_SEASONS
from analysis.drought_hindcast.download_fews_net import (
    CLASSIFICATIONS_ENCODING,
    FEWS_NET_COUNTRY_CODES,
    get_classifications_files,
    get_geographic_units_files,
)
from analysis.drought_hindcast.indicator_data import FEWS_NET_REGION_PHASES_FILE
from analysis.drought_hindcast.study_area import load_region_geometries
from shapely.geometry import shape

PHASES = (1, 2, 3, 4, 5)
CRISIS_PHASE = 3
CRISIS_OR_WORSE_COLUMN = f"area_share_phase_{CRISIS_PHASE}_or_worse"
# The highest phase anywhere in the country, from the Food Assistance Outlook Brief.
# It is not a classification of areas.
HIGHEST_HOUSEHOLD_SCALE = "IPC Highest Household"
REPORT_COLUMNS = ["reporting_date", "scenario"]
REPORT_DETAIL_COLUMNS = ["projection_start", "projection_end", "source_document"]
CLASSIFICATION_COLUMNS = [
    "fnid",
    "classification_scale",
    "value",
    *REPORT_COLUMNS,
    *REPORT_DETAIL_COLUMNS,
]
OUTPUT_FLOAT_FORMAT = "%.4f"


def main() -> None:
    region_geometries = load_region_geometries()
    country_by_region_key = {
        region_season.region_key: region_season.country_code_iso3
        for region_season in REGION_SEASONS
    }

    region_tables: list[pd.DataFrame] = []
    for country_code_iso3 in FEWS_NET_COUNTRY_CODES:
        classifications = load_classifications(country_code_iso3)
        geographic_units = load_geographic_units(country_code_iso3)
        for region_key, geometry in region_geometries.items():
            if country_by_region_key[region_key] != country_code_iso3:
                continue
            region_phases = calculate_region_phases(
                classifications, select_unit_areas_in_region(geographic_units, geometry)
            )
            region_phases.insert(0, "region_key", region_key)
            region_tables.append(region_phases)
            print(
                f"{region_key}: {region_phases['reporting_date'].nunique()} reports, "
                f"{region_phases['reporting_date'].min()} to "
                f"{region_phases['reporting_date'].max()}"
            )

    FEWS_NET_REGION_PHASES_FILE.parent.mkdir(parents=True, exist_ok=True)
    all_region_phases = pd.concat(region_tables)
    all_region_phases.to_csv(
        FEWS_NET_REGION_PHASES_FILE, index=False, float_format=OUTPUT_FLOAT_FORMAT
    )
    print(f"Wrote {len(all_region_phases)} rows to {FEWS_NET_REGION_PHASES_FILE}")


def load_classifications(country_code_iso3: str) -> pd.DataFrame:
    """The classified areas of every report: one row per unit, report and scenario."""
    yearly_classifications = [
        pd.read_csv(path, encoding=CLASSIFICATIONS_ENCODING, low_memory=False)
        for path in get_classifications_files(country_code_iso3)
    ]
    # A year without classifications comes without the report columns.
    classifications = pd.concat(
        year_classifications[CLASSIFICATION_COLUMNS]
        for year_classifications in yearly_classifications
        if not year_classifications.empty
    )
    classifications = classifications[
        classifications["classification_scale"] != HIGHEST_HOUSEHOLD_SCALE
    ].dropna(subset="value")
    unknown_phases = set(classifications["value"]) - set(PHASES)
    if unknown_phases:
        raise ValueError(f"{country_code_iso3}: unknown phases {unknown_phases}")
    return classifications


def load_geographic_units(country_code_iso3: str) -> pd.DataFrame:
    """Area and centre of the units that cover an area; camps are points without one."""
    units = [
        unit
        for path in get_geographic_units_files(country_code_iso3)
        for unit in json.loads(path.read_text(encoding="utf-8"))
        if unit["area"] > 0
    ]
    return pd.DataFrame(
        {
            "fnid": [unit["fnid"] for unit in units],
            "area_km2": [unit["area"] for unit in units],
            "longitude": [unit["centroid"][0] for unit in units],
            "latitude": [unit["centroid"][1] for unit in units],
        }
    )


def select_unit_areas_in_region(
    geographic_units: pd.DataFrame, region_geometry: dict
) -> pd.Series:
    """Area of each unit that has its centre in the region."""
    is_in_region = shapely.contains_xy(
        shape(region_geometry),
        geographic_units["longitude"].to_numpy(),
        geographic_units["latitude"].to_numpy(),
    )
    return geographic_units[is_in_region].set_index("fnid")["area_km2"]


def calculate_region_phases(
    classifications: pd.DataFrame, area_by_unit: pd.Series
) -> pd.DataFrame:
    """Per report and scenario, the share of the classified area of the region in each phase."""
    region_classifications = classifications.join(area_by_unit, on="fnid", how="inner")
    area_by_phase = region_classifications.pivot_table(
        index=REPORT_COLUMNS,
        columns="value",
        values=area_by_unit.name,
        aggfunc="sum",
        fill_value=0,
    ).reindex(columns=PHASES, fill_value=0)
    classified_area = area_by_phase.sum(axis=1)

    region_phases = area_by_phase.div(classified_area, axis=0)
    region_phases.columns = [get_phase_share_column(phase) for phase in PHASES]
    region_phases[CRISIS_OR_WORSE_COLUMN] = region_phases[
        [get_phase_share_column(phase) for phase in PHASES if phase >= CRISIS_PHASE]
    ].sum(axis=1)
    region_phases.insert(0, "classified_area_km2", classified_area)
    reports = region_classifications.groupby(REPORT_COLUMNS)
    region_phases.insert(0, "unit_count", reports.size())
    # A few units have another projection period than the rest of their report.
    report_details = reports[REPORT_DETAIL_COLUMNS].agg(
        lambda values: values.mode().iloc[0]
    )
    return report_details.join(region_phases).reset_index()


def get_phase_share_column(phase: int) -> str:
    return f"area_share_phase_{phase}"


if __name__ == "__main__":
    main()
