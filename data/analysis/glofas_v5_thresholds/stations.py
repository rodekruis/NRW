"""The NRW GloFAS stations from a local clone of the seed repo, and the boxes their reanalysis is downloaded in."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from shared.data_helpers import target_countries_iso_a3

STATION_THRESHOLDS_DIRECTORY = Path("hazard/flood/glofas-stations")
GLOFAS_CELL_SIZE_DEGREES = 0.05


@dataclass(frozen=True)
class Station:
    country: str
    code: str
    name: str
    latitude: float
    longitude: float
    thresholds: dict[float, float]


@dataclass(frozen=True)
class DownloadBox:
    north: float
    west: float
    south: float
    east: float
    station_codes: tuple[str, ...]

    @property
    def name(self) -> str:
        """Named after its area, so boxes of different sizes do not share downloads."""
        return f"{self.north:g}_{self.west:g}_{self.south:g}_{self.east:g}"

    @property
    def area(self) -> list[float]:
        return [self.north, self.west, self.south, self.east]


def load_stations(seed_repo_path: Path) -> list[Station]:
    stations: list[Station] = []
    for country in sorted(target_countries_iso_a3):
        path = (
            seed_repo_path
            / STATION_THRESHOLDS_DIRECTORY
            / f"{country}_station_thresholds.json"
        )
        for entry in json.loads(path.read_text(encoding="utf-8")):
            stations.append(
                Station(
                    country=country,
                    code=str(entry["station_code"]),
                    name=str(entry["station_name"]),
                    latitude=float(entry["lat"]),
                    longitude=float(entry["lon"]),
                    thresholds={
                        float(threshold["return_period"]): float(
                            threshold["threshold_value"]
                        )
                        for threshold in entry["thresholds"]
                    },
                )
            )
    return stations


def group_into_boxes(
    stations: list[Station], maximum_span_degrees: float, padding_degrees: float
) -> list[DownloadBox]:
    """Greedy west-to-east grouping, so each box spans at most `maximum_span_degrees` before padding."""
    groups: list[list[Station]] = []
    for station in sorted(stations, key=lambda item: (item.longitude, item.latitude)):
        for group in groups:
            latitudes = [member.latitude for member in group] + [station.latitude]
            longitudes = [member.longitude for member in group] + [station.longitude]
            if (
                max(latitudes) - min(latitudes) <= maximum_span_degrees
                and max(longitudes) - min(longitudes) <= maximum_span_degrees
            ):
                group.append(station)
                break
        else:
            groups.append([station])

    return [
        DownloadBox(
            north=_round_outwards(
                max(member.latitude for member in group) + padding_degrees, up=True
            ),
            west=_round_outwards(
                min(member.longitude for member in group) - padding_degrees, up=False
            ),
            south=_round_outwards(
                min(member.latitude for member in group) - padding_degrees, up=False
            ),
            east=_round_outwards(
                max(member.longitude for member in group) + padding_degrees, up=True
            ),
            station_codes=tuple(member.code for member in group),
        )
        for group in groups
    ]


def _round_outwards(value: float, up: bool) -> float:
    cells = value / GLOFAS_CELL_SIZE_DEGREES
    rounded_cells = -(-cells // 1) if up else cells // 1
    return round(rounded_cells * GLOFAS_CELL_SIZE_DEGREES, 2)
