"""Download FEWS NET food insecurity classifications from the FEWS NET Data Warehouse."""

import csv
import gzip
from datetime import datetime, timedelta, UTC
from pathlib import Path

import requests
from analysis.drought_hindcast.indicator_data import (
    FEWS_NET_CLASSIFICATIONS_DIRECTORY,
    FEWS_NET_GEOGRAPHIC_UNITS_DIRECTORY,
)

FEWS_NET_API_URL = "https://fdw.fews.net/api"
# FEWS NET's two-letter code per study country.
FEWS_NET_COUNTRY_CODES: dict[str, str] = {
    "ETH": "ET",
    "KEN": "KE",
    "ZWE": "ZW",
    "LSO": "LS",
}
# The warehouse has no classifications of the study countries before 2011.
FIRST_YEAR = 2011
# Projected periods end in the year after their report at the latest.
PROJECTION_YEAR_COUNT = 1
# Reports are published and corrected up to some months after their month.
PUBLICATION_MARGIN = timedelta(days=90)
REQUEST_TIMEOUT_SECONDS = 600
CLASSIFICATIONS_ENCODING = "utf-8-sig"
UNIT_TYPE_COLUMN = "unit_type"


def main() -> None:
    FEWS_NET_CLASSIFICATIONS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    FEWS_NET_GEOGRAPHIC_UNITS_DIRECTORY.mkdir(parents=True, exist_ok=True)

    last_year = datetime.now(UTC).year + PROJECTION_YEAR_COUNT
    for country_code_iso3 in FEWS_NET_COUNTRY_CODES:
        for year in range(FIRST_YEAR, last_year + 1):
            _download_classifications(country_code_iso3, year)
        for unit_type in _list_unit_types(country_code_iso3):
            _download_geographic_units(country_code_iso3, unit_type)
    print(f"FEWS NET complete in {FEWS_NET_CLASSIFICATIONS_DIRECTORY.parent}")


def get_classifications_files(country_code_iso3: str) -> list[Path]:
    return sorted(
        FEWS_NET_CLASSIFICATIONS_DIRECTORY.glob(f"{country_code_iso3}_*.csv.gz")
    )


def get_geographic_units_files(country_code_iso3: str) -> list[Path]:
    return sorted(
        FEWS_NET_GEOGRAPHIC_UNITS_DIRECTORY.glob(f"{country_code_iso3}_*.json")
    )


def is_final(path: Path, year: int) -> bool:
    """A year stops changing once it was downloaded well after its end."""
    if not path.exists():
        return False
    downloaded_at = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    return downloaded_at > datetime(year + 1, 1, 1, tzinfo=UTC) + PUBLICATION_MARGIN


def _download_classifications(country_code_iso3: str, year: int) -> None:
    """One file per year, holding every classification of a period that ends in the year."""
    path = FEWS_NET_CLASSIFICATIONS_DIRECTORY / f"{country_code_iso3}_{year}.csv.gz"
    if is_final(path, year):
        return
    content = _download(
        "ipcphase",
        {
            "format": "csv",
            "country_code": FEWS_NET_COUNTRY_CODES[country_code_iso3],
            "start_date": f"{year}-01-01",
            "end_date": f"{year}-12-31",
        },
    )
    _write_atomically(path, gzip.compress(content))
    print(f"Downloaded {path.name}")


def _list_unit_types(country_code_iso3: str) -> list[str]:
    unit_types: set[str] = set()
    for path in get_classifications_files(country_code_iso3):
        with gzip.open(path, "rt", encoding=CLASSIFICATIONS_ENCODING) as file:
            unit_types.update(row[UNIT_TYPE_COLUMN] for row in csv.DictReader(file))
    return sorted(unit_types)


def _download_geographic_units(country_code_iso3: str, unit_type: str) -> None:
    """Name, area and centre of every unit; new versions of the units are added over time."""
    path = FEWS_NET_GEOGRAPHIC_UNITS_DIRECTORY / f"{country_code_iso3}_{unit_type}.json"
    content = _download(
        "geographicunit",
        {
            "format": "json",
            "country_code": FEWS_NET_COUNTRY_CODES[country_code_iso3],
            "unit_type": unit_type,
        },
    )
    _write_atomically(path, content)
    print(f"Downloaded {path.name}")


def _download(endpoint: str, parameters: dict[str, str]) -> bytes:
    response = requests.get(
        f"{FEWS_NET_API_URL}/{endpoint}/",
        params=parameters,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.content


def _write_atomically(path: Path, content: bytes) -> None:
    """Write via a temporary name, so an interrupted run leaves no file that looks complete."""
    partial_path = path.with_suffix(".part")
    partial_path.write_bytes(content)
    partial_path.rename(path)


if __name__ == "__main__":
    main()
