"""Load the flood pipeline's inputs from a local clone of the seed repo, without the NRW API."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from pipelines.infra.data_types.admin_area_types import (
    AdminArea,
    AdminAreaProperties,
    AdminAreasSet,
)
from pipelines.infra.data_types.flood_depth_provider import FloodDepthProvider
from pipelines.infra.data_types.loaded_data_types import AlertConfig, RasterData
from pipelines.infra.data_types.location_point import LocationPoint
from rasterio.transform import Affine
from shared.image_helpers import rgba_png_to_float_array

ADMIN_AREAS_DIRECTORY = Path("admin-areas/processed")
STATION_THRESHOLDS_DIRECTORY = Path("hazard/flood/glofas-stations")
FLOOD_DEPTH_DIRECTORY = Path("hazard/flood/flood-extents/data-png")
POPULATION_DIRECTORY = Path("exposure/population/data-png")

# Mirrors FLOOD_LEAD_TIME_SPECTRUM in api-service seed-alert-configs.const.ts.
FLOOD_LEAD_TIME_SPECTRUM = [f"{lead_time}-day" for lead_time in range(8)]


@dataclass
class LocalFloodDepthProvider(FloodDepthProvider):
    """Reads the flood maps from a local seed repo clone instead of downloading them."""

    directory: Path = field(default_factory=Path)
    _rasters: dict[int, RasterData] = field(default_factory=dict)

    def get_raster(self, return_period: int) -> RasterData:
        if return_period not in self._rasters:
            stem = f"{self.country}_flood_extent_rp{return_period}"
            self._rasters[return_period] = _read_png_raster(
                self.directory / f"{stem}.png",
                self.directory / f"{stem}_metadata.json",
            )
        return self._rasters[return_period]


def load_admin_areas(
    seed_repo_path: Path, country: str, admin_level: int
) -> AdminAreasSet:
    path = seed_repo_path / ADMIN_AREAS_DIRECTORY / f"{country}_adm{admin_level}.json"
    features = json.loads(path.read_text(encoding="utf-8"))["features"]
    admin_areas: dict[str, AdminArea] = {}
    for feature in features:
        properties = feature["properties"]
        place_code = str(properties[f"ADM{admin_level}_PCODE"])
        admin_areas[place_code] = AdminArea(
            properties=AdminAreaProperties(
                pcode=place_code,
                name=str(properties[f"ADM{admin_level}_EN"]),
                admin_level=admin_level,
                country_code=country,
                parent_pcodes={
                    level: str(properties[f"ADM{level}_PCODE"])
                    for level in range(admin_level)
                },
            ),
            geometry_type=feature["geometry"]["type"],
            coordinates=feature["geometry"]["coordinates"],
        )
    return AdminAreasSet(admin_areas=admin_areas)


def load_stations_and_alert_configs(
    seed_repo_path: Path, country: str, admin_level: int
) -> tuple[dict[str, LocationPoint], list[AlertConfig]]:
    path = (
        seed_repo_path
        / STATION_THRESHOLDS_DIRECTORY
        / f"{country}_station_thresholds.json"
    )
    stations: dict[str, LocationPoint] = {}
    alert_configs: list[AlertConfig] = []
    for entry in json.loads(path.read_text(encoding="utf-8")):
        station_code = str(entry["station_code"])
        stations[station_code] = LocationPoint(
            name=str(entry["station_name"]),
            lat=float(entry["lat"]),
            lon=float(entry["lon"]),
            id=station_code,
            attributes={"thresholds": entry["thresholds"]},
        )
        alert_configs.append(
            AlertConfig(
                spatial_extent_name=station_code,
                spatial_extent_place_codes=[
                    str(place_code)
                    for place_code in entry["pcodes"].get(str(admin_level), [])
                ],
                temporal_extents=[{"lead-time-spectrum": FLOOD_LEAD_TIME_SPECTRUM}],
            )
        )
    return stations, alert_configs


def load_flood_depth_provider(
    seed_repo_path: Path, country: str
) -> LocalFloodDepthProvider:
    directory = seed_repo_path / FLOOD_DEPTH_DIRECTORY
    manifest = json.loads(
        (directory / f"{country}_flood_extents_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    return LocalFloodDepthProvider(
        available_return_periods=manifest["return_periods"],
        base_url="",
        country=country,
        directory=directory,
    )


def load_population(seed_repo_path: Path, country: str) -> RasterData:
    directory = seed_repo_path / POPULATION_DIRECTORY
    return _read_png_raster(
        directory / f"{country}_population.png",
        directory / f"{country}_population_metadata.json",
    )


def _read_png_raster(png_path: Path, metadata_path: Path) -> RasterData:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    return RasterData(
        array=rgba_png_to_float_array(png_path.read_bytes()).astype(np.float32),
        transform=Affine(*metadata["transform"][:6]),
        crs=metadata["crs"],
        nodata=metadata["nodata"],
    )
