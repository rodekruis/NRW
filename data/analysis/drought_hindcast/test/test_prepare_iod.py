from pathlib import Path

import pandas as pd
import pytest
import xarray as xr
from analysis.drought_hindcast.prepare_iod import (
    parse_ersst,
    parse_hadisst,
    parse_oisst_jamstec,
    parse_oisst_weekly,
)


def test_hadisst_reads_one_value_per_month_and_drops_missing_months(
    tmp_path: Path,
) -> None:
    # Arrange
    path = tmp_path / "hadisst.data"
    path.write_text(
        "2025 2026\n"
        "2025 0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9 1.0 1.1 1.2\n"
        "2026 -0.1 -0.2 -9999.000 -9999.000 -9999.000 -9999.000"
        " -9999.000 -9999.000 -9999.000 -9999.000 -9999.000 -9999.000\n"
        "-9999\n"
        "DMI HadISST1.1\n",
        encoding="utf-8",
    )

    # Act
    index = parse_hadisst(path)

    # Assert
    assert len(index) == 14
    assert index[pd.Period("2025-12")] == pytest.approx(1.2)
    assert index.index[-1] == pd.Period("2026-02")
    assert index.iloc[-1] == pytest.approx(-0.2)


def test_ersst_reads_the_difference_between_the_poles_below_the_header(
    tmp_path: Path,
) -> None:
    # Arrange
    path = tmp_path / "ersst.txt"
    path.write_text(
        "Climatology : 1991-2020\n"
        "\n"
        "  Year   Month     WTIO      SETIO       DMI\n"
        "\n"
        "  2026     7       0.68       0.39       0.29\n"
        "  2026     8       0.71       0.04       0.68\n",
        encoding="utf-8",
    )

    # Act
    index = parse_ersst(path)

    # Assert
    assert index.to_dict() == {pd.Period("2026-07"): 0.29, pd.Period("2026-08"): 0.68}


def test_oisst_weekly_averages_the_weeks_of_a_month_and_drops_an_incomplete_month(
    tmp_path: Path,
) -> None:
    # Arrange
    weeks = pd.date_range("2026-08-02", "2026-09-13", freq="7D")
    path = tmp_path / "oisst.nc"
    xr.Dataset(
        {"DMI": ("TIME", [0.1, 0.2, 0.3, 0.4, 0.5, 9.0, 9.0])}, coords={"TIME": weeks}
    ).to_netcdf(path)

    # Act
    index = parse_oisst_weekly(path)

    # Assert
    assert index.to_dict() == {pd.Period("2026-08"): pytest.approx(0.3)}


def test_jamstec_keeps_the_observed_months_and_not_the_forecast_months(
    tmp_path: Path,
) -> None:
    # Arrange
    path = tmp_path / "jamstec.csv"
    path.write_text(
        "time,Obs,Mean\n2026-09-15,0.68,\n2026-10-15,0.94,0.8\n2026-11-15,,0.7\n",
        encoding="utf-8",
    )

    # Act
    index = parse_oisst_jamstec(path)

    # Assert
    assert index.to_dict() == {pd.Period("2026-09"): 0.68, pd.Period("2026-10"): 0.94}
