"""Download CHIRPS monthly rainfall (final product) cropped to the study area."""

import re
import time
from concurrent.futures import ThreadPoolExecutor
from http import HTTPStatus
from pathlib import Path

import numpy as np
import rasterio
import requests
from analysis.drought_hindcast.study_area import (
    Bounds,
    CHIRPS_DIRECTORY,
    FIRST_YEAR,
    load_study_bounds,
)
from rasterio.io import MemoryFile
from rasterio.profiles import Profile
from rasterio.windows import from_bounds

CHIRPS_VERSION = "v3.0"
CHIRPS_MONTHLY_URL = (
    f"https://data.chc.ucsb.edu/products/CHIRPS/{CHIRPS_VERSION}/monthly/africa/tifs/"
)
CHIRPS_FILE_NAME_PATTERN = re.compile(
    rf'href="(chirps-{re.escape(CHIRPS_VERSION)}\.(\d{{4}})\.\d{{2}}\.tif)"'
)
REQUEST_TIMEOUT_SECONDS = 120
# The server limits the speed per connection, and answers 429 (Too Many Requests)
# when requests follow each other too quickly.
DOWNLOAD_WORKER_COUNT = 4
RATE_LIMIT_WAIT_SECONDS = 5
MAXIMUM_ATTEMPTS = 6
COMPRESSION = "deflate"
# The source files mark sea with this value without declaring it as nodata.
NO_DATA_VALUE = -9999


def main() -> None:
    bounds = load_study_bounds()
    CHIRPS_DIRECTORY.mkdir(parents=True, exist_ok=True)

    available_file_names = _list_available_file_names()
    missing_file_names = [
        file_name
        for file_name in available_file_names
        if not (CHIRPS_DIRECTORY / file_name).exists()
    ]
    print(
        f"{len(available_file_names)} months available "
        f"({available_file_names[0]} to {available_file_names[-1]}), "
        f"{len(missing_file_names)} to download"
    )
    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKER_COUNT) as executor:
        list(
            executor.map(
                lambda file_name: _download_cropped(file_name, bounds),
                missing_file_names,
            )
        )
    print(f"CHIRPS complete in {CHIRPS_DIRECTORY}")


def _list_available_file_names() -> list[str]:
    listing = _download(CHIRPS_MONTHLY_URL).decode()
    return sorted(
        file_name
        for file_name, year in CHIRPS_FILE_NAME_PATTERN.findall(listing)
        if int(year) >= FIRST_YEAR
    )


def _download_cropped(file_name: str, bounds: Bounds) -> None:
    content = _download(CHIRPS_MONTHLY_URL + file_name)
    with MemoryFile(content) as memory_file, memory_file.open() as source:
        window = (
            from_bounds(
                bounds.west,
                bounds.south,
                bounds.east,
                bounds.north,
                transform=source.transform,
            )
            .round_offsets()
            .round_lengths()
        )
        rainfall = source.read(window=window)
        profile = source.profile
        profile.update(
            height=rainfall.shape[1],
            width=rainfall.shape[2],
            transform=source.window_transform(window),
            compress=COMPRESSION,
            nodata=NO_DATA_VALUE,
        )
    _write_atomically(CHIRPS_DIRECTORY / file_name, rainfall, profile)
    print(f"Downloaded {file_name}")


def _download(url: str) -> bytes:
    for attempt in range(1, MAXIMUM_ATTEMPTS + 1):
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code != HTTPStatus.TOO_MANY_REQUESTS:
            response.raise_for_status()
            return response.content
        time.sleep(RATE_LIMIT_WAIT_SECONDS * attempt)
    raise RuntimeError(f"Still rate-limited after {MAXIMUM_ATTEMPTS} attempts: {url}")


def _write_atomically(path: Path, rainfall: np.ndarray, profile: Profile) -> None:
    """Write via a temporary name, so an interrupted run leaves no file that looks complete."""
    partial_path = path.with_suffix(".part")
    with rasterio.open(partial_path, "w", **profile) as target:
        target.write(rainfall)
    partial_path.rename(path)


if __name__ == "__main__":
    main()
