"""Build per-country GloFAS return period curves for the seed repo from ECMWF's global GloFAS auxiliary files."""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import xarray as xr
from data_management.seed_data_management.admin_areas.admin_area_dataset_helpers import (
    Bounds,
    get_country_bounds,
)
from pipelines.constants import DEFAULT_CRS
from pipelines.flood.constants import GLOFAS_VERSION
from pipelines.infra.data_types.glofas_return_period_curves import (
    get_glofas_return_period_curves_filename,
    GlofasReturnPeriodCurves,
)
from rasterio.transform import from_origin
from shared.data_helpers import get_seed_data_repo_path, target_countries_iso_a3
from shared.download_helpers import download_file

# Linked from https://confluence.ecmwf.int/spaces/CEMS/pages/242067380/Auxiliary+Data
GLOFAS_AUXILIARY_DATA_URL = (
    "https://confluence.ecmwf.int/download/attachments/242067380"
)
DEFAULT_CACHE_DIRECTORY = Path(__file__).parents[3] / "data" / "glofas-auxiliary-cache"
RETURN_PERIOD_CURVES_DIRECTORY = Path("hazard/flood/glofas-return-period-curves")
STATION_THRESHOLDS_DIRECTORY = Path("hazard/flood/glofas-stations")
DEFAULT_PADDING_DEGREES = 0.5

LATITUDE = "lat"
LONGITUDE = "lon"
LOCATION = "location"
SCALE = "scale"
UPSTREAM_AREA = "upstream_area"


@dataclass(frozen=True)
class GlobalFile:
    filename: str
    variable: str
    latitude: str
    longitude: str


@dataclass(frozen=True)
class GlobalFiles:
    location: GlobalFile
    scale: GlobalFile
    upstream_area: GlobalFile


GLOBAL_FILES_BY_GLOFAS_VERSION = {
    "v4": GlobalFiles(
        location=GlobalFile("flood_threshold_glofas_v4_mu.nc", "mu", "lat", "lon"),
        scale=GlobalFile("flood_threshold_glofas_v4_sigma.nc", "sigma", "lat", "lon"),
        upstream_area=GlobalFile(
            "uparea_glofas_v4_0.nc", "uparea", "latitude", "longitude"
        ),
    ),
}


def main() -> None:
    arguments = parse_arguments()
    seed_repo_path = get_seed_data_repo_path()
    output_directory: Path = (
        arguments.output_directory or seed_repo_path / RETURN_PERIOD_CURVES_DIRECTORY
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    global_curves = load_global_curves(
        arguments.glofas_version, arguments.cache_directory
    )

    for country in arguments.countries:
        curves = clip_to_bounds(
            global_curves,
            get_forecast_bounds(seed_repo_path, country),
            arguments.padding_degrees,
        )
        output_path = output_directory / get_glofas_return_period_curves_filename(
            country, arguments.glofas_version
        )
        curves.write_geotiff(output_path)
        print(
            f"{country}: {output_path.name}, {curves.location.shape[0]} x {curves.location.shape[1]} cells, "
            f"{np.count_nonzero(np.isfinite(curves.location))} with a curve"
        )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--countries", nargs="+", default=sorted(target_countries_iso_a3)
    )
    parser.add_argument(
        "--glofas-version",
        choices=sorted(GLOBAL_FILES_BY_GLOFAS_VERSION),
        default=GLOFAS_VERSION,
    )
    parser.add_argument(
        "--padding-degrees", type=float, default=DEFAULT_PADDING_DEGREES
    )
    parser.add_argument("--cache-directory", type=Path, default=DEFAULT_CACHE_DIRECTORY)
    parser.add_argument(
        "--output-directory",
        type=Path,
        help="Defaults to glofas-return-period-curves in the seed repo",
    )
    return parser.parse_args()


def load_global_curves(glofas_version: str, cache_directory: Path) -> xr.Dataset:
    """The three global files as one dataset. They are read lazily, so only the clipped cells are loaded."""
    global_files = GLOBAL_FILES_BY_GLOFAS_VERSION[glofas_version]
    variables = {
        LOCATION: _open_global_file(
            global_files.location, glofas_version, cache_directory
        ),
        SCALE: _open_global_file(global_files.scale, glofas_version, cache_directory),
        UPSTREAM_AREA: _open_global_file(
            global_files.upstream_area, glofas_version, cache_directory
        ),
    }

    reference = variables[LOCATION]
    for name, variable in variables.items():
        for coordinate in (LATITUDE, LONGITUDE):
            if not np.array_equal(reference[coordinate], variable[coordinate]):
                raise ValueError(
                    f"Global '{name}' is on a different {coordinate} grid than '{LOCATION}'"
                )

    return xr.Dataset(variables)


def get_forecast_bounds(seed_repo_path: Path, country: str) -> Bounds:
    """The country and its stations, like the bounds the pipeline slices the forecast to. Stations can lie outside the country."""
    minimum_longitude, minimum_latitude, maximum_longitude, maximum_latitude = (
        get_country_bounds(seed_repo_path, country)
    )
    stations = json.loads(
        (
            seed_repo_path
            / STATION_THRESHOLDS_DIRECTORY
            / f"{country}_station_thresholds.json"
        ).read_text(encoding="utf-8")
    )
    latitudes = [station["lat"] for station in stations]
    longitudes = [station["lon"] for station in stations]
    return (
        min([minimum_longitude, *longitudes]),
        min([minimum_latitude, *latitudes]),
        max([maximum_longitude, *longitudes]),
        max([maximum_latitude, *latitudes]),
    )


def clip_to_bounds(
    global_curves: xr.Dataset, bounds: Bounds, padding_degrees: float
) -> GlofasReturnPeriodCurves:
    """The cells whose centre lies inside the padded bounds. Coordinates are cell centres, north first."""
    minimum_longitude, minimum_latitude, maximum_longitude, maximum_latitude = bounds
    clipped = global_curves.sel(
        {
            LATITUDE: slice(
                maximum_latitude + padding_degrees, minimum_latitude - padding_degrees
            ),
            LONGITUDE: slice(
                minimum_longitude - padding_degrees, maximum_longitude + padding_degrees
            ),
        }
    )
    if clipped.sizes[LATITUDE] == 0 or clipped.sizes[LONGITUDE] == 0:
        raise ValueError(f"No GloFAS cells inside bounds {bounds}")

    cell_size = _get_cell_size(global_curves)
    return GlofasReturnPeriodCurves(
        location=clipped[LOCATION].to_numpy().astype(np.float64),
        scale=clipped[SCALE].to_numpy().astype(np.float64),
        upstream_area=clipped[UPSTREAM_AREA].to_numpy().astype(np.float64),
        transform=from_origin(
            float(clipped[LONGITUDE][0]) - cell_size / 2,
            float(clipped[LATITUDE][0]) + cell_size / 2,
            cell_size,
            cell_size,
        ),
        crs=DEFAULT_CRS,
    )


def _open_global_file(
    global_file: GlobalFile, glofas_version: str, cache_directory: Path
) -> xr.DataArray:
    path = download_file(
        f"{GLOFAS_AUXILIARY_DATA_URL}/{global_file.filename}",
        cache_directory / glofas_version / global_file.filename,
    )
    return xr.open_dataset(path)[global_file.variable].rename(
        {global_file.latitude: LATITUDE, global_file.longitude: LONGITUDE}
    )


def _get_cell_size(global_curves: xr.Dataset) -> float:
    latitudes = global_curves[LATITUDE].to_numpy()
    longitudes = global_curves[LONGITUDE].to_numpy()
    if latitudes[0] < latitudes[-1] or longitudes[0] > longitudes[-1]:
        raise ValueError("Expected latitudes north first and longitudes west first")
    latitude_cell_size = (latitudes[0] - latitudes[-1]) / (len(latitudes) - 1)
    longitude_cell_size = (longitudes[-1] - longitudes[0]) / (len(longitudes) - 1)
    if not np.isclose(latitude_cell_size, longitude_cell_size):
        raise ValueError(
            f"Expected square cells, got {latitude_cell_size} x {longitude_cell_size} degrees"
        )
    return float(longitude_cell_size)


if __name__ == "__main__":
    main()
