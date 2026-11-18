"""Average CHIRPS monthly rainfall over each region."""

import re

import numpy as np
import rasterio
import xarray as xr
from analysis.drought_hindcast.region_weights import calculate_cell_weights
from analysis.drought_hindcast.study_area import (
    CHIRPS_DIRECTORY,
    describe_outdated_download,
    load_region_geometries,
    load_study_bounds,
    OBSERVED_RAINFALL_FILE,
)

CHIRPS_CELL_SIZE_DEGREES = 0.05
# A cell counts as inside a region when its centre is.
CHIRPS_SUBCELL_COUNT = 1
CHIRPS_MONTH_PATTERN = re.compile(r"\.(\d{4})\.(\d{2})\.tif$")


def main() -> None:
    bounds = load_study_bounds()
    weights_by_region = {
        region_key: calculate_cell_weights(
            geometry, bounds, CHIRPS_CELL_SIZE_DEGREES, CHIRPS_SUBCELL_COUNT
        )
        for region_key, geometry in load_region_geometries().items()
    }

    paths = sorted(CHIRPS_DIRECTORY.glob("*.tif"))
    months = np.array([_parse_month(path.name) for path in paths])
    _check_months_are_consecutive(months)

    rainfall = np.empty((len(weights_by_region), len(paths)))
    for month_position, path in enumerate(paths):
        with rasterio.open(path) as source:
            if not np.allclose(
                source.bounds,
                (bounds.west, bounds.south, bounds.east, bounds.north),
                atol=CHIRPS_CELL_SIZE_DEGREES / 2,
            ):
                raise ValueError(
                    f"{path.name} covers {tuple(source.bounds)}, not the study area. "
                    + describe_outdated_download(CHIRPS_DIRECTORY, "download_chirps")
                )
            cell_rainfall = source.read(1, masked=True)
        for region_position, weights in enumerate(weights_by_region.values()):
            rainfall[region_position, month_position] = np.ma.average(
                cell_rainfall, weights=weights
            )

    OBSERVED_RAINFALL_FILE.parent.mkdir(parents=True, exist_ok=True)
    xr.DataArray(
        rainfall,
        dims=("region", "month"),
        coords={
            "region": list(weights_by_region),
            "month": months.astype("datetime64[ns]"),
        },
        name="rainfall_mm",
    ).to_netcdf(OBSERVED_RAINFALL_FILE)
    print(
        f"Wrote {len(weights_by_region)} regions x {len(paths)} months "
        f"({months[0]} to {months[-1]}) to {OBSERVED_RAINFALL_FILE}"
    )


def _parse_month(file_name: str) -> np.datetime64:
    match = CHIRPS_MONTH_PATTERN.search(file_name)
    if match is None:
        raise ValueError(f"No year and month in file name {file_name}")
    return np.datetime64(f"{match.group(1)}-{match.group(2)}", "M")


def _check_months_are_consecutive(months: np.ndarray) -> None:
    gaps = np.flatnonzero(np.diff(months).astype(int) != 1)
    if gaps.size:
        raise ValueError(f"CHIRPS months missing after {months[gaps]}")


if __name__ == "__main__":
    main()
