"""Convert SEAS5 monthly rainfall to mm per month for the grid cells that overlap a region."""

from pathlib import Path

import numpy as np
import xarray as xr
from analysis.drought_hindcast.definitions import LEAD_MONTH_COUNT
from analysis.drought_hindcast.region_weights import calculate_cell_weights
from analysis.drought_hindcast.study_area import (
    Bounds,
    describe_outdated_download,
    FORECAST_RAINFALL_FILE,
    load_region_geometries,
    load_study_bounds,
    SEAS5_DIRECTORY,
)

SEAS5_CELL_SIZE_DEGREES = 1
# Number of subcells per cell side used to measure how much of a cell lies in a region.
SEAS5_SUBCELL_COUNT = 20
SECONDS_PER_DAY = 86400
MILLIMETRES_PER_METRE = 1000
COMPRESSION_LEVEL = 4


def main() -> None:
    bounds = load_study_bounds()
    geometries = load_region_geometries()
    # [region, row, column]
    cell_weights = np.stack(
        [
            calculate_cell_weights(
                geometry, bounds, SEAS5_CELL_SIZE_DEGREES, SEAS5_SUBCELL_COUNT
            )
            for geometry in geometries.values()
        ]
    )
    is_in_any_region = cell_weights.sum(axis=0) > 0
    latitudes, longitudes = _get_cell_centres(bounds)

    yearly_rainfall: list[xr.DataArray] = []
    for path in sorted(SEAS5_DIRECTORY.glob("*.grib")):
        rainfall = _read_rainfall_mm(path)
        _check_grid(rainfall, latitudes, longitudes, path)
        print(
            f"{path.name}: {rainfall.sizes['start']} start months, "
            f"{rainfall.sizes['member']} members"
        )
        yearly_rainfall.append(
            xr.DataArray(
                rainfall.values[..., is_in_any_region],
                dims=("start", "lead", "member", "cell"),
                coords={name: rainfall[name] for name in ("start", "lead", "member")},
            )
        )

    row_positions, column_positions = np.nonzero(is_in_any_region)
    dataset = xr.Dataset(
        {
            # Years with fewer members are filled with NaN.
            "rainfall_mm": xr.concat(yearly_rainfall, dim="start", join="outer"),
            "cell_weight": (("region", "cell"), cell_weights[:, is_in_any_region]),
        },
        coords={
            "region": list(geometries),
            "latitude": ("cell", latitudes[row_positions]),
            "longitude": ("cell", longitudes[column_positions]),
        },
    )
    FORECAST_RAINFALL_FILE.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_netcdf(
        FORECAST_RAINFALL_FILE,
        encoding={"rainfall_mm": {"zlib": True, "complevel": COMPRESSION_LEVEL}},
    )
    print(
        f"Wrote {dataset.sizes['start']} start months x {dataset.sizes['cell']} cells "
        f"to {FORECAST_RAINFALL_FILE}"
    )


def _get_cell_centres(bounds: Bounds) -> tuple[np.ndarray, np.ndarray]:
    half_cell = SEAS5_CELL_SIZE_DEGREES / 2
    latitudes = np.arange(
        bounds.north - half_cell, bounds.south, -SEAS5_CELL_SIZE_DEGREES
    )
    longitudes = np.arange(
        bounds.west + half_cell, bounds.east, SEAS5_CELL_SIZE_DEGREES
    )
    return latitudes, longitudes


def _read_rainfall_mm(path: Path) -> xr.DataArray:
    """Rainfall in mm per month with dimensions start, lead, member, latitude, longitude."""
    rainfall_rate = (
        xr.open_dataset(
            path,
            engine="cfgrib",
            backend_kwargs={"time_dims": ("forecastMonth", "time"), "indexpath": ""},
        )["tprate"]
        .rename({"time": "start", "forecastMonth": "lead", "number": "member"})
        .transpose("start", "lead", "member", "latitude", "longitude")
        .load()
    )
    if rainfall_rate.isnull().any():
        raise ValueError(f"{path.name} has missing values")
    if list(rainfall_rate["lead"].values) != list(range(1, LEAD_MONTH_COUNT + 1)):
        raise ValueError(f"{path.name} has leads {rainfall_rate['lead'].values}")

    # Lead 1 is the start month itself.
    months_after_start = (rainfall_rate["lead"].values - 1).astype("timedelta64[M]")
    target_months = (
        rainfall_rate["start"].values.astype("datetime64[M]")[:, np.newaxis]
        + months_after_start[np.newaxis, :]
    )
    days_in_target_month = (
        (target_months + np.timedelta64(1, "M")).astype("datetime64[D]")
        - target_months.astype("datetime64[D]")
    ).astype(int)
    millimetres_per_metre_per_second = xr.DataArray(
        days_in_target_month * SECONDS_PER_DAY * MILLIMETRES_PER_METRE,
        dims=("start", "lead"),
    )
    return rainfall_rate * millimetres_per_metre_per_second


def _check_grid(
    rainfall: xr.DataArray, latitudes: np.ndarray, longitudes: np.ndarray, path: Path
) -> None:
    if not (
        np.array_equal(rainfall["latitude"].values, latitudes)
        and np.array_equal(rainfall["longitude"].values, longitudes)
    ):
        raise ValueError(
            f"{path.name} is not on the grid of the study area. "
            + describe_outdated_download(SEAS5_DIRECTORY, "download_seas5")
        )


if __name__ == "__main__":
    main()
