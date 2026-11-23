"""Download GloFAS v4 and v5 daily discharge around the NRW stations from the CEMS Early Warning Data Store."""

from __future__ import annotations

import argparse
import os
from concurrent.futures import as_completed, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import requests
import xarray as xr
from analysis.glofas_v5_thresholds.station_cells import locate_station_cell, StationCell
from analysis.glofas_v5_thresholds.stations import (
    DownloadBox,
    GLOFAS_CELL_SIZE_DEGREES,
    group_into_boxes,
    load_stations,
)
from data_management.seed_data_management.flood.build_glofas_return_period_curves import (
    DEFAULT_CACHE_DIRECTORY,
    load_global_curves,
)
from ecmwf.datastores import Client
from shared.data_helpers import get_seed_data_repo_path

EARLY_WARNING_DATA_STORE_URL = "https://ewds.climate.copernicus.eu/api"
COLLECTION = "cems-glofas-historical"
DEFAULT_DOWNLOAD_DIRECTORY = Path(__file__).parents[2] / "data" / "glofas-reanalysis"
# The Climate and Early Warning Data Stores share one ECMWF account and API key.
API_KEY_ENVIRONMENT_VARIABLE = "CDSAPI_KEY"
DEFAULT_MAXIMUM_SPAN_DEGREES = 30.0
# The data store runs a user's requests one by one; a few in its queue keep it busy.
DEFAULT_PARALLEL_REQUESTS = 4
# Cells on each side of a station that are kept, to find the river cell in v5.
WINDOW_RADIUS_CELLS = 3
PADDING_DEGREES = 0.15
LAST_YEAR = 2025
MONTHS = [f"{month:02d}" for month in range(1, 13)]
DAYS = [f"{day:02d}" for day in range(1, 32)]

STATION = "station"
ROW = "row"
COLUMN = "column"
TIME = "time"
DISCHARGE = "discharge"


@dataclass(frozen=True)
class GlofasVersion:
    system_version: str
    first_year: int


GLOFAS_VERSIONS = {
    "v4": GlofasVersion("version_4_0", 1979),
    "v5": GlofasVersion("version_5_0", 1980),
}


def main() -> None:
    arguments = parse_arguments()
    # Also loads data/.env, which holds the API key.
    stations = [
        station
        for station in load_stations(get_seed_data_repo_path())
        if not arguments.countries or station.country in arguments.countries
    ]
    boxes = group_into_boxes(stations, arguments.maximum_span_degrees, PADDING_DEGREES)
    print(f"{len(stations)} stations in {len(boxes)} boxes")
    for box in boxes:
        print(f"{box.name}: {len(box.station_codes)} stations")
    v4_curves = load_global_curves("v4", DEFAULT_CACHE_DIRECTORY)
    station_cells = {
        station.code: locate_station_cell(station, v4_curves) for station in stations
    }

    for version_name in arguments.versions:
        version = GLOFAS_VERSIONS[version_name]
        version_directory = arguments.download_directory / version_name
        if not arguments.extract_only:
            download_version(
                version,
                version_directory,
                boxes,
                _create_client(),
                arguments.parallel_requests,
            )
        output_path = (
            arguments.download_directory / f"station_discharge_{version_name}.nc"
        )
        extract_station_windows(
            version, version_directory, boxes, station_cells
        ).to_netcdf(output_path)
        print(f"{version_name}: wrote {output_path}")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--versions", nargs="+", choices=sorted(GLOFAS_VERSIONS), default=["v4", "v5"]
    )
    parser.add_argument(
        "--countries", nargs="+", help="Only the stations of these countries"
    )
    parser.add_argument(
        "--maximum-span-degrees",
        type=float,
        default=DEFAULT_MAXIMUM_SPAN_DEGREES,
        help="The data store runs one request at a time and the area barely matters, so few large boxes are fastest",
    )
    parser.add_argument(
        "--parallel-requests", type=int, default=DEFAULT_PARALLEL_REQUESTS
    )
    parser.add_argument(
        "--download-directory", type=Path, default=DEFAULT_DOWNLOAD_DIRECTORY
    )
    parser.add_argument(
        "--extract-only",
        action="store_true",
        help="Skip downloading and only extract the station windows from files already downloaded",
    )
    return parser.parse_args()


def download_version(
    version: GlofasVersion,
    version_directory: Path,
    boxes: list[DownloadBox],
    client: Client,
    parallel_requests: int,
) -> None:
    """One request per box and year, the most the data store allows. Files already downloaded are skipped."""
    jobs = [
        (box, year)
        for box in boxes
        for year in range(version.first_year, LAST_YEAR + 1)
        if not _get_download_path(version_directory, box, year).exists()
    ]
    print(f"{version.system_version}: {len(jobs)} requests to download")

    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=parallel_requests) as executor:
        futures = {
            executor.submit(
                _download_box_year, client, version, version_directory, box, year
            ): f"{box.name} {year}"
            for box, year in jobs
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            label = futures[future]
            try:
                future.result()
                print(f"[{completed}/{len(jobs)}] {label}")
            except (requests.RequestException, OSError) as error:
                failures.append(f"{label}: {error}")
                print(f"[{completed}/{len(jobs)}] {label} failed: {error}")

    if failures:
        raise RuntimeError(
            f"{len(failures)} requests failed, rerun to retry them:\n"
            + "\n".join(failures)
        )


def extract_station_windows(
    version: GlofasVersion,
    version_directory: Path,
    boxes: list[DownloadBox],
    station_cells: dict[str, StationCell],
) -> xr.Dataset:
    """Daily discharge in a square window of cells around each station, with the station's cell in the middle.

    Reads one year at a time, as a large box over all years does not fit in memory.
    """
    windows: list[xr.Dataset] = []
    for box in boxes:
        yearly_windows: dict[str, list[xr.DataArray]] = {
            station_code: [] for station_code in box.station_codes
        }
        for year in range(version.first_year, LAST_YEAR + 1):
            discharge = _open_box_year(_get_download_path(version_directory, box, year))
            for station_code in box.station_codes:
                yearly_windows[station_code].append(
                    _select_window(discharge, station_cells[station_code])
                )
        for station_code, station_windows in yearly_windows.items():
            window = xr.concat(station_windows, dim=TIME)
            windows.append(
                xr.Dataset(
                    {
                        DISCHARGE: (
                            (ROW, COLUMN, TIME),
                            window.transpose("latitude", "longitude", TIME).to_numpy(),
                        ),
                        "cell_latitude": ((ROW,), window["latitude"].to_numpy()),
                        "cell_longitude": ((COLUMN,), window["longitude"].to_numpy()),
                    },
                    coords={TIME: window[TIME].to_numpy()},
                ).expand_dims({STATION: [station_code]})
            )
    return xr.concat(windows, dim=STATION)


def _select_window(discharge: xr.DataArray, cell: StationCell) -> xr.DataArray:
    """Cells outside the downloaded box are left empty."""
    offsets = np.arange(-WINDOW_RADIUS_CELLS, WINDOW_RADIUS_CELLS + 1)
    return discharge.reindex(
        latitude=np.round(cell.latitude - offsets * GLOFAS_CELL_SIZE_DEGREES, 3),
        longitude=np.round(cell.longitude + offsets * GLOFAS_CELL_SIZE_DEGREES, 3),
        method="nearest",
        tolerance=GLOFAS_CELL_SIZE_DEGREES / 4,
    ).load()


def _create_client() -> Client:
    """Without the key in the environment, the client falls back to its own configuration file."""
    key = next(
        (
            value
            for name, value in os.environ.items()
            if name.upper() == API_KEY_ENVIRONMENT_VARIABLE
        ),
        None,
    )
    client = Client(url=EARLY_WARNING_DATA_STORE_URL, key=key)
    client.check_authentication()
    return client


def _download_box_year(
    client: Client,
    version: GlofasVersion,
    version_directory: Path,
    box: DownloadBox,
    year: int,
) -> None:
    path = _get_download_path(version_directory, box, year)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = path.with_suffix(".partial")
    client.retrieve(
        COLLECTION,
        {
            "system_version": [version.system_version],
            "hydrological_model": ["lisflood"],
            "product_type": ["consolidated"],
            "timespan": ["time_mean"],
            "variable": ["average_river_discharge_in_the_last_24_hours"],
            "year": [str(year)],
            "month": MONTHS,
            "day": DAYS,
            "data_format": "netcdf",
            "download_format": "unarchived",
            "area": box.area,
        },
        target=str(partial_path),
    )
    partial_path.rename(path)


def _get_download_path(version_directory: Path, box: DownloadBox, year: int) -> Path:
    return version_directory / box.name / f"{year}.nc"


def _open_box_year(path: Path) -> xr.DataArray:
    dataset = xr.open_dataset(path)
    (variable,) = dataset.data_vars
    discharge = dataset[variable]
    time_dimension = next(
        dimension
        for dimension in discharge.dims
        if np.issubdtype(discharge[dimension].dtype, np.datetime64)
    )
    # Time stamps mark the end of each 24-hour average; shift them to its start, so a year's days stay in that year.
    discharge = discharge.assign_coords(
        {time_dimension: discharge[time_dimension] - np.timedelta64(1, "D")}
    )
    return discharge.rename({time_dimension: TIME}).squeeze(drop=True)


if __name__ == "__main__":
    main()
