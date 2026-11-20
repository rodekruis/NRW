from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
import xarray as xr
from pipelines.constants import DEFAULT_CRS
from pipelines.flood.forecast import calculate_flood_forecasts
from pipelines.infra.data_provider import DataProvider
from pipelines.infra.data_submitter import DataSubmitter
from pipelines.infra.data_types.admin_area_types import (
    AdminArea,
    AdminAreaProperties,
    AdminAreasSet,
)
from pipelines.infra.data_types.data_config_types import DataSource, OutputMode
from pipelines.infra.data_types.dtos import Alert
from pipelines.infra.data_types.enums import (
    EnsembleMemberType,
    ForecastSource,
    HazardType,
)
from pipelines.infra.data_types.flood_depth_provider import FloodDepthProvider
from pipelines.infra.data_types.glofas_return_period_curves import (
    GlofasReturnPeriodCurves,
)
from pipelines.infra.data_types.loaded_data_types import (
    AlertConfig,
    DataType,
    LoadedDataSource,
    RasterData,
)
from pipelines.infra.data_types.location_point import LocationPoint
from pipelines.infra.utils.alert_admin_aggregation import (
    aggregate_to_parent_admin_levels,
)
from pipelines.infra.utils.alert_centroid import compute_alert_centroid
from rasterio.transform import from_origin

# 2 x 2 GloFAS cells of 0.05 degree under a flood map and a population raster of 10 x 10 pixels.
# The station is in the north-west cell, the only cell in flood.
_COUNTRY = "TST"
_ADMIN_LEVEL = 1
_STATION_CODE = "G0001"
_WEST = 35.0
_NORTH = -16.0
_CELL_SIZE = 0.05
_PIXEL_SIZE = 0.01
_PIXELS_PER_CELL = 5
_WEST_PLACE_CODE = "TS01"
_EAST_PLACE_CODE = "TS02"

_GUMBEL_LOCATION = 1000.0
_GUMBEL_SCALE = 100.0
_RETURN_PERIODS = (1.5, 2.0, 5.0, 10.0, 20.0)
# Between the 2- and 5-year thresholds: 3.25 years on the continuous curve.
_FLOOD_DISCHARGE = 1100.0
_CALM_DISCHARGE = 10.0
_TEN_YEAR_DEPTH = 2.0
_PEOPLE_PER_PIXEL = 1.0


@dataclass
class _InMemoryFloodDepthProvider(FloodDepthProvider):
    rasters: dict[int, RasterData] = field(default_factory=dict)

    def get_raster(self, return_period: int) -> RasterData:
        return self.rasters[return_period]


def _make_pixel_raster(value: float) -> RasterData:
    return RasterData(
        array=np.full((10, 10), value, dtype=np.float32),
        transform=from_origin(_WEST, _NORTH, _PIXEL_SIZE, _PIXEL_SIZE),
        crs=DEFAULT_CRS,
        nodata=0.0,
    )


def _make_admin_area(place_code: str, west: float) -> AdminArea:
    east, south = west + _CELL_SIZE, _NORTH - 2 * _CELL_SIZE
    return AdminArea(
        properties=AdminAreaProperties(
            pcode=place_code,
            name=place_code,
            admin_level=_ADMIN_LEVEL,
            country_code=_COUNTRY,
            parent_pcodes={0: "TS"},
        ),
        geometry_type="Polygon",
        coordinates=[
            [
                [west, south],
                [west, _NORTH],
                [east, _NORTH],
                [east, south],
                [west, south],
            ]
        ],
    )


def _write_forecast(directory: Path) -> list[str]:
    discharge = np.full((2, 2, 2), _CALM_DISCHARGE, dtype=np.float32)
    discharge[:, 0, 0] = _FLOOD_DISCHARGE
    paths: list[str] = []
    for member in range(2):
        path = directory / f"dis_{member:02d}_2026090200_sliced_{_COUNTRY}.nc"
        xr.Dataset(
            {"dis": (["time", "lat", "lon"], discharge)},
            coords={
                "time": [0, 1],
                "lat": [_NORTH - _CELL_SIZE / 2, _NORTH - 3 * _CELL_SIZE / 2],
                "lon": [_WEST + _CELL_SIZE / 2, _WEST + 3 * _CELL_SIZE / 2],
            },
        ).to_netcdf(path)
        paths.append(str(path))
    return paths


def _make_data_provider(
    directory: Path, place_code: str, ten_year_depth: float = _TEN_YEAR_DEPTH
) -> DataProvider:
    station = LocationPoint(
        name="Test station",
        lat=_NORTH - _CELL_SIZE / 2,
        lon=_WEST + _CELL_SIZE / 2,
        id=_STATION_CODE,
        attributes={
            "thresholds": [
                {
                    "return_period": return_period,
                    "threshold_value": _GUMBEL_LOCATION
                    - _GUMBEL_SCALE * np.log(-np.log(1 - 1 / return_period)),
                }
                for return_period in _RETURN_PERIODS
            ]
        },
    )
    data_by_source: dict[DataSource, tuple[DataType, object]] = {
        DataSource.ALERT_CONFIGS_NRW_API: (
            DataType.ALERT_CONFIG_LIST,
            [
                AlertConfig(
                    spatial_extent_name=_STATION_CODE,
                    spatial_extent_place_codes=[place_code],
                    temporal_extents=[{"lead-time-spectrum": ["0-day", "1-day"]}],
                )
            ],
        ),
        DataSource.GLOFAS_STATIONS_NRW_API: (
            DataType.LOCATION_POINT_DICT,
            {_STATION_CODE: station},
        ),
        DataSource.ADMIN_AREA_NRW_API: (
            DataType.ADMIN_AREA_SET,
            AdminAreasSet(
                admin_areas={
                    _WEST_PLACE_CODE: _make_admin_area(_WEST_PLACE_CODE, _WEST),
                    _EAST_PLACE_CODE: _make_admin_area(
                        _EAST_PLACE_CODE, _WEST + _CELL_SIZE
                    ),
                }
            ),
        ),
        DataSource.FLOOD_DEPTH_SEED_REPO: (
            DataType.FLOOD_DEPTH_PROVIDER,
            _InMemoryFloodDepthProvider(
                available_return_periods=[10],
                base_url="http://mock/",
                country=_COUNTRY,
                rasters={10: _make_pixel_raster(ten_year_depth)},
            ),
        ),
        DataSource.GLOFAS_RETURN_PERIOD_CURVES_SEED_REPO: (
            DataType.GLOFAS_RETURN_PERIOD_CURVES,
            GlofasReturnPeriodCurves(
                location=np.full((2, 2), _GUMBEL_LOCATION),
                scale=np.full((2, 2), _GUMBEL_SCALE),
                upstream_area=np.full((2, 2), 1e10),
                transform=from_origin(_WEST, _NORTH, _CELL_SIZE, _CELL_SIZE),
                crs=DEFAULT_CRS,
            ),
        ),
        DataSource.POPULATION_NRW_API: (
            DataType.RASTER_DATA,
            _make_pixel_raster(_PEOPLE_PER_PIXEL),
        ),
        DataSource.GLOFAS_DISCHARGE_FTP: (
            DataType.PATH_LIST,
            _write_forecast(directory),
        ),
    }
    data_provider = DataProvider(MagicMock(), local_data="country")
    for data_source, (data_type, data) in data_by_source.items():
        data_provider.loaded_data[data_source] = LoadedDataSource(
            data_type=data_type, data_source=data_source, data=data
        )
    return data_provider


def _run_forecast(data_provider: DataProvider, directory: Path) -> list[Alert]:
    """Run the flood forecast and the steps that follow it up to the integrity checks."""
    data_submitter = DataSubmitter(MagicMock())
    data_submitter.set_forecast_metadata(
        issued_at=datetime(2026, 9, 2, tzinfo=UTC),
        hazard_type=HazardType.FLOODS,
        forecast_sources=[ForecastSource.GLOFAS_RIVER_DISCHARGE],
        country_code_iso3=_COUNTRY,
    )
    calculate_flood_forecasts(data_provider, data_submitter, _COUNTRY, _ADMIN_LEVEL)
    admin_areas = data_provider.get_data(DataSource.ADMIN_AREA_NRW_API, AdminAreasSet)
    for alert in data_submitter.get_alerts():
        alert.centroid = compute_alert_centroid(alert, admin_areas)
        aggregate_to_parent_admin_levels(alert, admin_areas)
    errors = data_submitter.send_all(OutputMode.LOCAL, str(directory / "output"))
    assert errors == []
    return data_submitter.get_alerts()


def _get_exposed_population(alert: Alert) -> dict[str, float | bool]:
    return {
        admin_area.place_code: admin_area.value
        for admin_area in alert.exposure.admin_areas
        if admin_area.admin_level == _ADMIN_LEVEL
    }


@pytest.fixture
def working_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Alerting forecast files are archived under the data cache directory.
    monkeypatch.setenv("DATA_CACHE_DIR", str(tmp_path / "cache"))
    return tmp_path


def test_alert_exposes_the_population_around_the_cell_in_flood(working_directory: Path):
    # Arrange: the station's area holds the cell in flood and a calm cell south of it
    data_provider = _make_data_provider(working_directory, _WEST_PLACE_CODE)

    # Act
    alerts = _run_forecast(data_provider, working_directory)

    # Assert: only the pixels of the cell in flood are exposed
    assert len(alerts) == 1
    assert _get_exposed_population(alerts[0]) == {
        _WEST_PLACE_CODE: _PIXELS_PER_CELL**2 * _PEOPLE_PER_PIXEL
    }
    median_return_periods = {
        severity.severity_value
        for severity in alerts[0].severity
        if severity.ensemble_member_type == EnsembleMemberType.MEDIAN
    }
    assert median_return_periods == {2.0}


def test_alert_stays_when_its_footprint_is_empty(working_directory: Path):
    # Arrange: the station triggers, but its area only holds calm cells
    data_provider = _make_data_provider(working_directory, _EAST_PLACE_CODE)

    # Act
    alerts = _run_forecast(data_provider, working_directory)

    # Assert
    assert len(alerts) == 1
    assert _get_exposed_population(alerts[0]) == {_EAST_PLACE_CODE: 0.0}
    assert len(alerts[0].severity) > 0


def test_no_alert_when_the_flood_maps_do_not_cover_the_area(working_directory: Path):
    # Arrange
    data_provider = _make_data_provider(
        working_directory, _WEST_PLACE_CODE, ten_year_depth=0.0
    )

    # Act
    alerts = _run_forecast(data_provider, working_directory)

    # Assert
    assert alerts == []
