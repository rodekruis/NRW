from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pytest
from pipelines.constants import DEFAULT_CRS
from pipelines.flood.compute_flood_depth import (
    compute_flood_depth,
    determine_cell_return_periods,
)
from pipelines.flood.determine_alerts import TimeIntervalReturnPeriodSeverity
from pipelines.flood.footprint_method import RegriddingMethod
from pipelines.infra.data_types.flood_depth_provider import FloodDepthProvider
from pipelines.infra.data_types.glofas_return_period_curves import (
    GlofasReturnPeriodCurves,
)
from pipelines.infra.data_types.loaded_data_types import RasterData
from rasterio.transform import from_origin
from shapely.geometry import box

_FLOOD_MAP_NODATA = 0.0
_MAXIMUM_RETURN_PERIOD = 500.0
_LARGE_UPSTREAM_AREA = 1e10
_SMALL_UPSTREAM_AREA = 1e8
# Two GloFAS cells of 1 degree, west and east, under a flood map of 2 x 4 pixels of 0.5 degree.
_CELL_TRANSFORM = from_origin(0, 1, 1, 1)
_FLOOD_MAP_TRANSFORM = from_origin(0, 1, 0.5, 0.5)
_WHOLE_MAP = box(0, 0, 2, 1)


@dataclass
class _InMemoryFloodDepthProvider(FloodDepthProvider):
    rasters: dict[int, RasterData] = field(default_factory=dict)

    def get_raster(self, return_period: int) -> RasterData:
        return self.rasters[return_period]


def _make_provider(depth_by_return_period: dict[int, float]) -> FloodDepthProvider:
    return _InMemoryFloodDepthProvider(
        available_return_periods=sorted(depth_by_return_period),
        base_url="http://mock/",
        country="MWI",
        rasters={
            return_period: RasterData(
                array=np.full((2, 4), depth, dtype=np.float32),
                transform=_FLOOD_MAP_TRANSFORM,
                crs=DEFAULT_CRS,
                nodata=_FLOOD_MAP_NODATA,
            )
            for return_period, depth in depth_by_return_period.items()
        },
    )


def _make_severities(return_period: float) -> list[TimeIntervalReturnPeriodSeverity]:
    return [
        TimeIntervalReturnPeriodSeverity(
            time_interval_start="2026-09-02T00:00:00Z",
            time_interval_end="2026-09-02T23:59:59Z",
            median_return_period=return_period,
            ensemble_return_periods=[return_period],
        )
    ]


def _make_cell_return_periods(west: float, east: float) -> RasterData:
    return RasterData(
        array=np.array([[west, east]]),
        transform=_CELL_TRANSFORM,
        crs=DEFAULT_CRS,
        nodata=np.nan,
    )


def _make_curves(
    upstream_area: tuple[float, float] = (_LARGE_UPSTREAM_AREA, _LARGE_UPSTREAM_AREA),
    scale: tuple[float, float] = (100.0, 100.0),
) -> GlofasReturnPeriodCurves:
    return GlofasReturnPeriodCurves(
        location=np.array([[1000.0, 1000.0]]),
        scale=np.array([scale]),
        upstream_area=np.array([upstream_area]),
        transform=_CELL_TRANSFORM,
        crs=DEFAULT_CRS,
    )


def _make_discharge(west: float, east: float) -> RasterData:
    return RasterData(
        array=np.array([[west, east]], dtype=np.float32),
        transform=_CELL_TRANSFORM,
        crs=DEFAULT_CRS,
        nodata=np.nan,
    )


def test_flood_depth_follows_the_return_period_of_each_cell():
    # Arrange: the west cell is calm, the east cell is at 5.5 years
    provider = _make_provider({10: 1.0, 20: 2.0})

    # Act
    flood_depth = compute_flood_depth(
        time_interval_severities=_make_severities(5.0),
        cell_return_periods=_make_cell_return_periods(1.1, 5.5),
        boundary=_WHOLE_MAP,
        flood_depth_provider=provider,
        regridding_method=RegriddingMethod.NEAREST,
        minimum_flood_depth=0.0,
    )

    # Assert
    assert flood_depth is not None
    np.testing.assert_allclose(flood_depth.array[:, :2], 0.0)
    np.testing.assert_allclose(flood_depth.array[:, 2:], 0.5)
    assert flood_depth.transform == _FLOOD_MAP_TRANSFORM


def test_flood_depth_is_clipped_to_the_boundary():
    # Arrange: the boundary covers only the two westernmost pixel columns
    provider = _make_provider({10: 1.0})

    # Act
    flood_depth = compute_flood_depth(
        time_interval_severities=_make_severities(5.0),
        cell_return_periods=_make_cell_return_periods(5.5, 5.5),
        boundary=box(0, 0, 1, 1),
        flood_depth_provider=provider,
        minimum_flood_depth=0.0,
    )

    # Assert
    assert flood_depth is not None
    assert flood_depth.array.shape == (2, 2)
    np.testing.assert_allclose(flood_depth.array, 0.5)


def test_flood_depth_leaves_out_depths_below_the_minimum():
    # Arrange: west at 2.8 years gives 0.2 m, east at 1.9 years gives 0.1 m
    provider = _make_provider({10: 1.0})

    # Act
    flood_depth = compute_flood_depth(
        time_interval_severities=_make_severities(2.0),
        cell_return_periods=_make_cell_return_periods(2.8, 1.9),
        boundary=_WHOLE_MAP,
        flood_depth_provider=provider,
        minimum_flood_depth=0.15,
    )

    # Assert
    assert flood_depth is not None
    np.testing.assert_allclose(flood_depth.array[:, :2], 0.2, atol=1e-6)
    np.testing.assert_allclose(flood_depth.array[:, 2:], 0.0)


def test_flood_depth_is_empty_when_no_cell_reaches_the_minimum_return_period():
    # Arrange: the station triggers at 2 years, but both cells in its area are calm
    provider = _make_provider({10: 1.0})

    # Act
    flood_depth = compute_flood_depth(
        time_interval_severities=_make_severities(2.0),
        cell_return_periods=_make_cell_return_periods(1.1, 1.2),
        boundary=_WHOLE_MAP,
        flood_depth_provider=provider,
    )

    # Assert
    assert flood_depth is not None
    assert not flood_depth.array.any()


def test_flood_depth_follows_the_minimum_return_period():
    # Arrange: the west cell is at 1.4 years, below the default minimum of 1.5 years
    provider = _make_provider({10: 1.0})
    cell_return_periods = _make_cell_return_periods(1.4, 1.0)

    # Act
    with_default_minimum = compute_flood_depth(
        time_interval_severities=_make_severities(2.0),
        cell_return_periods=cell_return_periods,
        boundary=_WHOLE_MAP,
        flood_depth_provider=provider,
        minimum_flood_depth=0.0,
    )
    with_lower_minimum = compute_flood_depth(
        time_interval_severities=_make_severities(2.0),
        cell_return_periods=cell_return_periods,
        boundary=_WHOLE_MAP,
        flood_depth_provider=provider,
        minimum_flood_depth=0.0,
        minimum_return_period=1.0,
    )

    # Assert: 0.4 years above the zero-depth return period, of the 9 years up to the 10-year map
    assert with_default_minimum is not None
    assert with_lower_minimum is not None
    assert not with_default_minimum.array.any()
    np.testing.assert_allclose(with_lower_minimum.array[:, :2], 0.4 / 9, atol=1e-6)
    np.testing.assert_allclose(with_lower_minimum.array[:, 2:], 0.0)


@pytest.mark.parametrize(
    "cell_return_periods", [None, _make_cell_return_periods(np.nan, np.nan)]
)
def test_flood_depth_falls_back_to_the_station_return_period(
    cell_return_periods: RasterData | None,
):
    # Arrange
    provider = _make_provider({10: 1.0})

    # Act
    flood_depth = compute_flood_depth(
        time_interval_severities=_make_severities(5.5),
        cell_return_periods=cell_return_periods,
        boundary=_WHOLE_MAP,
        flood_depth_provider=provider,
        minimum_flood_depth=0.0,
    )

    # Assert
    assert flood_depth is not None
    np.testing.assert_allclose(flood_depth.array, 0.5)


def test_flood_depth_is_none_when_the_flood_map_does_not_cover_the_boundary():
    # Arrange
    provider = _make_provider({10: 0.0})

    # Act
    flood_depth = compute_flood_depth(
        time_interval_severities=_make_severities(5.0),
        cell_return_periods=_make_cell_return_periods(5.5, 5.5),
        boundary=_WHOLE_MAP,
        flood_depth_provider=provider,
    )

    # Assert
    assert flood_depth is None


def test_cell_return_periods_use_the_curve_of_each_cell():
    # Arrange: the west cell is at its 2-year discharge, the east cell far below its curve
    two_year_discharge = 1000.0 - 100.0 * np.log(-np.log(0.5))

    # Act
    cell_return_periods = determine_cell_return_periods(
        median_discharge=_make_discharge(two_year_discharge, 10.0),
        return_period_curves=_make_curves(),
        maximum_return_period=_MAXIMUM_RETURN_PERIOD,
    )

    # Assert
    assert cell_return_periods is not None
    np.testing.assert_allclose(cell_return_periods.array, [[2.0, 1.0]], rtol=1e-6)


def test_small_streams_and_flat_curves_do_not_drive_the_footprint():
    # Arrange
    small_stream = _make_curves(
        upstream_area=(_SMALL_UPSTREAM_AREA, _LARGE_UPSTREAM_AREA)
    )
    flat_curve = _make_curves(scale=(0.001, 100.0))
    discharge = _make_discharge(1200.0, 1200.0)

    # Act
    without_small_stream = determine_cell_return_periods(
        discharge, small_stream, _MAXIMUM_RETURN_PERIOD
    )
    without_flat_curve = determine_cell_return_periods(
        discharge, flat_curve, _MAXIMUM_RETURN_PERIOD
    )

    # Assert
    for cell_return_periods in (without_small_stream, without_flat_curve):
        assert cell_return_periods is not None
        assert np.isnan(cell_return_periods.array[0, 0])
        assert np.isfinite(cell_return_periods.array[0, 1])


def test_cells_without_discharge_do_not_drive_the_footprint():
    # Arrange
    discharge = _make_discharge(np.nan, 1200.0)

    # Act
    cell_return_periods = determine_cell_return_periods(
        discharge, _make_curves(), _MAXIMUM_RETURN_PERIOD
    )

    # Assert
    assert cell_return_periods is not None
    assert np.isnan(cell_return_periods.array[0, 0])
    assert np.isfinite(cell_return_periods.array[0, 1])


def test_cell_return_periods_are_none_without_a_gridded_forecast():
    # Act
    cell_return_periods = determine_cell_return_periods(
        None, _make_curves(), _MAXIMUM_RETURN_PERIOD
    )

    # Assert
    assert cell_return_periods is None


def test_cell_return_periods_are_none_when_the_forecast_is_half_a_cell_off():
    # Arrange: the grid of the mock forecasts, whose cell centres lie on the corners of GloFAS cells
    discharge = RasterData(
        array=np.array([[1200.0, 1200.0]], dtype=np.float32),
        transform=from_origin(0.5, 1.5, 1, 1),
        crs=DEFAULT_CRS,
        nodata=np.nan,
    )

    # Act
    cell_return_periods = determine_cell_return_periods(
        discharge, _make_curves(), _MAXIMUM_RETURN_PERIOD
    )

    # Assert
    assert cell_return_periods is None
