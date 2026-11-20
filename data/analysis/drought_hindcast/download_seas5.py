"""Download ECMWF SEAS5 monthly rainfall hindcasts and forecasts for the study area."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, UTC
from pathlib import Path

import cdsapi
import requests
from analysis.drought_hindcast.study_area import (
    Bounds,
    FIRST_YEAR,
    load_study_bounds,
    SEAS5_DIRECTORY,
)
from dotenv import load_dotenv

ENVIRONMENT_FILE = Path(__file__).parents[2] / ".env"
CDS_API_URL = "https://cds.climate.copernicus.eu/api"
SEAS5_DATASET = "seasonal-monthly-single-levels"
CONSTRAINTS_URL = f"{CDS_API_URL}/retrieve/v1/processes/{SEAS5_DATASET}/constraints"
CONSTRAINTS_TIMEOUT_SECONDS = 60
# System 51 is the only SEAS5 version on the CDS that spans the whole period.
SEAS5_SYSTEM = "51"
SEAS5_SELECTION: dict[str, str | list[str]] = {
    "originating_centre": "ecmwf",
    "system": SEAS5_SYSTEM,
    "variable": ["total_precipitation"],
    "product_type": ["monthly_mean"],
}
LEAD_TIME_MONTHS = ["1", "2", "3", "4", "5", "6"]
CONCURRENT_REQUEST_COUNT = 4


def main() -> None:
    load_dotenv(ENVIRONMENT_FILE)
    bounds = load_study_bounds()
    SEAS5_DIRECTORY.mkdir(parents=True, exist_ok=True)

    years = range(FIRST_YEAR, datetime.now(UTC).year + 1)
    with ThreadPoolExecutor(max_workers=CONCURRENT_REQUEST_COUNT) as executor:
        list(executor.map(lambda year: _download_year(year, bounds), years))
    print(f"SEAS5 complete in {SEAS5_DIRECTORY}")


def _download_year(year: int, bounds: Bounds) -> None:
    """One file per year, named after the start months it holds so a growing year is refreshed."""
    months = _get_available_months(year)
    if not months:
        print(f"{year}: no start months available")
        return
    year_file_prefix = f"seas5_system{SEAS5_SYSTEM}_total_precipitation_{year}_"
    path = SEAS5_DIRECTORY / f"{year_file_prefix}{months[0]}-{months[-1]}.grib"
    if path.exists():
        return

    partial_path = path.with_suffix(".part")
    cdsapi.Client(url=CDS_API_URL).retrieve(
        SEAS5_DATASET,
        {
            **SEAS5_SELECTION,
            "year": [str(year)],
            "month": months,
            "leadtime_month": LEAD_TIME_MONTHS,
            "data_format": "grib",
            "area": [bounds.north, bounds.west, bounds.south, bounds.east],
        },
        str(partial_path),
    )
    partial_path.rename(path)
    for superseded_path in SEAS5_DIRECTORY.glob(f"{year_file_prefix}*.grib"):
        if superseded_path != path:
            superseded_path.unlink()
    print(f"Downloaded {path.name}")


def _get_available_months(year: int) -> list[str]:
    response = requests.post(
        CONSTRAINTS_URL,
        json={"inputs": {**SEAS5_SELECTION, "year": [str(year)]}},
        timeout=CONSTRAINTS_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return sorted(response.json()["month"])


if __name__ == "__main__":
    main()
