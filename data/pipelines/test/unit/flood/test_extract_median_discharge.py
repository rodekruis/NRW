from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import xarray as xr
from pipelines.flood.extract_forecast import (
    determine_peak_lead_time,
    extract_median_discharge,
    TimeIntervalDischarge,
)

_TEMPORAL_EXTENT = {"lead-time-spectrum": ["0-day", "1-day", "2-day"]}
_FILL_VALUE = -9999.0


def _write_ensemble_member(
    directory: Path, member: int, discharge_per_lead_time: list[list[list[float]]]
) -> str:
    """One GloFAS file: time x lat x lon, on 2 x 2 cells of 0.05 degree, north first. Both rows get the same discharge."""
    path = directory / f"dis_{member:02d}_2026090200_sliced_MWI.nc"
    xr.Dataset(
        {
            "dis": (
                ["time", "lat", "lon"],
                np.repeat(
                    np.array(discharge_per_lead_time, dtype=np.float32), 2, axis=1
                ),
            )
        },
        coords={
            "time": np.arange(len(discharge_per_lead_time)),
            "lat": [-16.025, -16.075],
            "lon": [35.025, 35.075],
        },
    ).to_netcdf(path)
    return str(path)


def _make_time_interval_discharges(
    ensemble_discharges_per_lead_time: list[list[float]],
) -> list[TimeIntervalDischarge]:
    return [
        TimeIntervalDischarge(
            time_interval_start=f"2026-09-0{lead_time + 2}T00:00:00Z",
            time_interval_end=f"2026-09-0{lead_time + 2}T23:59:59Z",
            ensemble_discharges=ensemble_discharges,
        )
        for lead_time, ensemble_discharges in enumerate(
            ensemble_discharges_per_lead_time
        )
    ]


def test_takes_the_ensemble_median_at_the_lead_time(tmp_path: Path):
    # Arrange: three members and two lead times; the west cell peaks at lead time 1, the east cell at lead time 0
    netcdf_paths = [
        _write_ensemble_member(tmp_path, 0, [[[10.0, 7.0]], [[40.0, 1.0]]]),
        _write_ensemble_member(tmp_path, 1, [[[20.0, 8.0]], [[50.0, 2.0]]]),
        _write_ensemble_member(tmp_path, 2, [[[90.0, 9.0]], [[30.0, 6.0]]]),
    ]

    # Act
    median_discharge = extract_median_discharge(netcdf_paths, lead_time=1)

    # Assert: both cells are taken at lead time 1, also the east cell that peaked earlier
    assert median_discharge is not None
    np.testing.assert_allclose(median_discharge.array, [[40.0, 2.0], [40.0, 2.0]])
    assert median_discharge.transform.a == pytest.approx(0.05)
    assert median_discharge.transform.e == pytest.approx(-0.05)
    assert median_discharge.transform.c == pytest.approx(35.0)
    assert median_discharge.transform.f == pytest.approx(-16.0)


def test_cells_without_discharge_are_empty(tmp_path: Path):
    # Arrange: the mock forecasts mark cells without a station with an undeclared fill value
    netcdf_paths = [
        _write_ensemble_member(tmp_path, 0, [[[10.0, _FILL_VALUE]]]),
        _write_ensemble_member(tmp_path, 1, [[[np.nan, _FILL_VALUE]]]),
    ]

    # Act
    median_discharge = extract_median_discharge(netcdf_paths, lead_time=0)

    # Assert
    assert median_discharge is not None
    np.testing.assert_array_equal(median_discharge.array[:, 0], [10.0, 10.0])
    assert np.isnan(median_discharge.array[:, 1]).all()


def test_is_none_without_forecast_files(tmp_path: Path):
    # Act
    median_discharge = extract_median_discharge(
        [str(tmp_path / "missing.nc")], lead_time=0
    )

    # Assert
    assert median_discharge is None


def test_is_none_when_the_forecast_does_not_reach_the_lead_time(tmp_path: Path):
    # Arrange
    netcdf_paths = [_write_ensemble_member(tmp_path, 0, [[[10.0, 1.0]]])]

    # Act
    median_discharge = extract_median_discharge(netcdf_paths, lead_time=1)

    # Assert
    assert median_discharge is None


def test_peak_lead_time_is_where_the_median_discharge_is_highest():
    # Arrange: medians are 20, 50 and 30; the highest single member is at lead time 0
    time_interval_discharges = _make_time_interval_discharges(
        [[10.0, 20.0, 900.0], [40.0, 50.0, 60.0], [30.0, 30.0, np.nan]]
    )

    # Act
    peak_lead_time = determine_peak_lead_time(
        time_interval_discharges, _TEMPORAL_EXTENT
    )

    # Assert
    assert peak_lead_time == 1


def test_peak_lead_time_is_the_earliest_of_equal_peaks():
    # Arrange
    time_interval_discharges = _make_time_interval_discharges([[10.0], [50.0], [50.0]])

    # Act
    peak_lead_time = determine_peak_lead_time(
        time_interval_discharges, _TEMPORAL_EXTENT
    )

    # Assert
    assert peak_lead_time == 1


def test_peak_lead_time_counts_from_the_first_lead_time_of_the_temporal_extent():
    # Arrange
    temporal_extent = {"lead-time-spectrum": ["3-day", "4-day"]}
    time_interval_discharges = _make_time_interval_discharges([[10.0], [50.0]])

    # Act
    peak_lead_time = determine_peak_lead_time(time_interval_discharges, temporal_extent)

    # Assert
    assert peak_lead_time == 4


def test_peak_lead_time_needs_discharge():
    # Arrange
    time_interval_discharges = _make_time_interval_discharges([[np.nan], []])

    # Act / Assert
    with pytest.raises(ValueError, match="No discharge"):
        determine_peak_lead_time(time_interval_discharges, _TEMPORAL_EXTENT)
