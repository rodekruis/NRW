"""Compare GloFAS v5 flood thresholds, computed from the v5 reanalysis with ECMWF's method, with today's v4 thresholds."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr
from analysis.glofas_v5_thresholds.download_reanalysis import (
    DEFAULT_DOWNLOAD_DIRECTORY,
    DISCHARGE,
    LAST_YEAR,
    STATION,
    TIME,
    WINDOW_RADIUS_CELLS,
)
from analysis.glofas_v5_thresholds.gumbel import fit_gumbel, gumbel_threshold
from analysis.glofas_v5_thresholds.station_cells import (
    locate_station_cell,
    RIVER_SEARCH_RADIUS_CELLS,
    StationCell,
)
from analysis.glofas_v5_thresholds.stations import load_stations, Station
from data_management.seed_data_management.flood.build_glofas_return_period_curves import (
    DEFAULT_CACHE_DIRECTORY,
    LATITUDE,
    load_global_curves,
    LOCATION,
    LONGITUDE,
    SCALE,
)
from pipelines.flood.constants import MINIMUM_RETURN_PERIOD_YEARS
from shared.data_helpers import get_seed_data_repo_path

RESULTS_DIRECTORY = Path(__file__).parent / "results"
COMPARISON_FILENAME = "station_threshold_comparison.csv"
RETURN_PERIODS = [1.5, 2.0, 5.0, 10.0, 20.0]
# The period of ECMWF's published v4 thresholds, see https://confluence.ecmwf.int/spaces/CEMS/pages/715612883/GloFAS+flood+threshold+generation
V4_PUBLISHED_FIRST_YEAR = 1979
V4_PUBLISHED_LAST_YEAR = 2022
V5_FIRST_YEAR = 1980
TREND_REFERENCE_YEAR = LAST_YEAR
RECENT_YEARS = 10
# A neighbouring v5 cell with at least this many times the flow of the station's cell is the station's river in v5.
NEIGHBOURING_RIVER_FACTOR = 2.0


@dataclass
class TrendAdjustment:
    slope_per_year: float
    r_squared: float
    adjusted_annual_maxima: np.ndarray


# One row of the results table per station.
type TableRow = dict[str, str | float | bool]


def main() -> None:
    arguments = parse_arguments()
    stations = {
        station.code: station for station in load_stations(get_seed_data_repo_path())
    }
    v5 = xr.open_dataset(arguments.download_directory / "station_discharge_v5.nc")
    v4_path = arguments.download_directory / "station_discharge_v4.nc"
    v4 = xr.open_dataset(v4_path) if v4_path.exists() else None
    v4_station_codes = set(v4[STATION].to_numpy()) if v4 is not None else set()
    v4_curves = load_global_curves("v4", DEFAULT_CACHE_DIRECTORY)

    table = pd.DataFrame(
        [
            compare_station(
                stations[str(code)],
                locate_station_cell(stations[str(code)], v4_curves),
                v5.sel({STATION: code}),
                v4_curves,
                (
                    v4.sel({STATION: code})
                    if v4 is not None and code in v4_station_codes
                    else None
                ),
            )
            for code in v5[STATION].to_numpy()
        ]
    )

    RESULTS_DIRECTORY.mkdir(exist_ok=True)
    table.to_csv(RESULTS_DIRECTORY / COMPARISON_FILENAME, index=False)
    print_summary(table)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--download-directory", type=Path, default=DEFAULT_DOWNLOAD_DIRECTORY
    )
    return parser.parse_args()


def compare_station(
    station: Station,
    cell: StationCell,
    v5: xr.Dataset,
    v4_curves: xr.Dataset,
    v4: xr.Dataset | None,
) -> TableRow:
    v5_annual_maxima = _annual_maxima(v5[DISCHARGE]).sel(
        year=slice(V5_FIRST_YEAR, LAST_YEAR)
    )
    v5_centre = _centre(v5_annual_maxima)
    v4_cell = v4_curves.sel(
        {LATITUDE: cell.latitude, LONGITUDE: cell.longitude}, method="nearest"
    )
    published_location = float(v4_cell[LOCATION])
    published_scale = float(v4_cell[SCALE])
    v4_thresholds = {
        return_period: gumbel_threshold(
            return_period, published_location, published_scale
        )
        for return_period in RETURN_PERIODS
    }
    # The mean of the fitted v4 Gumbel distribution, so no v4 reanalysis is needed.
    v4_mean_annual_maximum = published_location + np.euler_gamma * published_scale

    # The v5 thresholds are those of the station's river in v5, which can be the cell next to it.
    v5_river_row, v5_river_column = _find_v5_river_cell(
        v5_annual_maxima, v4_mean_annual_maximum
    )
    v5_river = v5_annual_maxima.isel(row=v5_river_row, column=v5_river_column)
    v5_thresholds = compute_v5_thresholds(v5_river)
    v5_station_cell_thresholds = compute_v5_thresholds(v5_centre)

    comparison: TableRow = {
        "country": station.country,
        "station_code": station.code,
        "station_name": station.name,
        "latitude": station.latitude,
        "longitude": station.longitude,
        "cell_latitude": cell.latitude,
        "cell_longitude": cell.longitude,
        "placement": str(cell.placement),
        "touching_cells": cell.touching_cells,
        "v4_upstream_area_square_kilometres": cell.upstream_area_square_kilometres,
        "smallest_touching_upstream_area_square_kilometres": cell.smallest_touching_upstream_area_square_kilometres,
        "seed_thresholds_on_cell": cell.seed_thresholds_on_cell,
        "v4_mean_annual_maximum": v4_mean_annual_maximum,
        "v5_station_cell_mean_annual_maximum": float(v5_centre.mean()),
        "v5_mean_annual_maximum": float(v5_river.mean()),
        "v5_river_cell_offset": f"{v5_river_row - WINDOW_RADIUS_CELLS:+d},{v5_river_column - WINDOW_RADIUS_CELLS:+d}",
        "v5_station_next_to_river": (v5_river_row, v5_river_column)
        != (WINDOW_RADIUS_CELLS, WINDOW_RADIUS_CELLS),
        "v5_trend_per_decade_relative": v5_thresholds.trend_per_decade_relative,
        "v5_trend_r_squared": v5_thresholds.trend.r_squared,
        "v5_unadjusted_recent_trigger_years": _count_recent_trigger_years(
            v5_river, v5_thresholds.unadjusted[MINIMUM_RETURN_PERIOD_YEARS]
        ),
        "v5_recent_trigger_years": _count_recent_trigger_years(
            v5_river, v5_thresholds.adjusted[MINIMUM_RETURN_PERIOD_YEARS]
        ),
        # What happens when the v5 forecasts are compared with today's v4 thresholds.
        "v5_against_v4_threshold_recent_trigger_years": _count_recent_trigger_years(
            v5_river, v4_thresholds[MINIMUM_RETURN_PERIOD_YEARS]
        ),
        # Only where the v4 reanalysis is downloaded.
        "v4_reproduction_location_difference": np.nan,
        "v4_reproduction_scale_difference": np.nan,
        "v4_recent_trigger_years": np.nan,
        **_by_return_period("seed", station.thresholds),
        **_by_return_period("v4_reproduced", dict.fromkeys(RETURN_PERIODS, np.nan)),
        **_by_return_period("v4", v4_thresholds),
        **_by_return_period("v5_unadjusted", v5_thresholds.unadjusted),
        **_by_return_period("v5", v5_thresholds.adjusted),
        **_by_return_period("v5_station_cell", v5_station_cell_thresholds.adjusted),
    }
    if v4 is not None:
        v4_centre = _centre(_annual_maxima(v4[DISCHARGE]))
        reproduced_location, reproduced_scale = fit_gumbel(
            v4_centre.sel(
                year=slice(V4_PUBLISHED_FIRST_YEAR, V4_PUBLISHED_LAST_YEAR)
            ).to_numpy()
        )
        comparison["v4_reproduction_location_difference"] = (
            reproduced_location / published_location - 1
        )
        comparison["v4_reproduction_scale_difference"] = (
            reproduced_scale / published_scale - 1
        )
        comparison["v4_recent_trigger_years"] = _count_recent_trigger_years(
            v4_centre, v4_thresholds[MINIMUM_RETURN_PERIOD_YEARS]
        )
        comparison.update(
            _by_return_period(
                "v4_reproduced",
                {
                    return_period: gumbel_threshold(
                        return_period, reproduced_location, reproduced_scale
                    )
                    for return_period in RETURN_PERIODS
                },
            )
        )
    return comparison


@dataclass
class V5Thresholds:
    unadjusted: dict[float, float]
    adjusted: dict[float, float]
    trend: TrendAdjustment
    trend_per_decade_relative: float


def compute_v5_thresholds(annual_maxima: xr.DataArray) -> V5Thresholds:
    """The v5 thresholds of one cell, the old way (without the trend step) and ECMWF's new way."""
    values = annual_maxima.to_numpy()
    trend = adjust_for_trend(
        values, annual_maxima["year"].to_numpy(), TREND_REFERENCE_YEAR
    )
    unadjusted = fit_gumbel(values)
    adjusted = fit_gumbel(trend.adjusted_annual_maxima)
    return V5Thresholds(
        unadjusted={
            return_period: gumbel_threshold(return_period, *unadjusted)
            for return_period in RETURN_PERIODS
        },
        adjusted={
            return_period: gumbel_threshold(return_period, *adjusted)
            for return_period in RETURN_PERIODS
        },
        trend=trend,
        trend_per_decade_relative=10 * trend.slope_per_year / float(values.mean()),
    )


def adjust_for_trend(
    annual_maxima: np.ndarray, years: np.ndarray, reference_year: int
) -> TrendAdjustment:
    """ECMWF's v5 adjustment: shift each year by √R² of the linear trend to the reference year.

    See https://confluence.ecmwf.int/spaces/CEMS/pages/715612910/Handling+of+non-stationarity+in+the+flood+thresholds
    """
    slope, intercept = np.polyfit(years, annual_maxima, 1)
    fitted = slope * years + intercept
    residual_sum_of_squares = np.sum((annual_maxima - fitted) ** 2)
    total_sum_of_squares = np.sum((annual_maxima - annual_maxima.mean()) ** 2)
    r_squared = 1 - residual_sum_of_squares / total_sum_of_squares
    adjusted = np.maximum(
        0, annual_maxima + np.sqrt(r_squared) * slope * (reference_year - years)
    )
    return TrendAdjustment(float(slope), float(r_squared), adjusted)


def print_summary(table: pd.DataFrame) -> None:
    trigger = f"rp{MINIMUM_RETURN_PERIOD_YEARS:g}"
    ratio = table[f"v5_{trigger}"] / table[f"v4_{trigger}"]
    print(f"Stations compared: {len(table)}")
    print(
        "v4 reproduction, largest difference in location / scale: "
        f"{table['v4_reproduction_location_difference'].abs().max():.1%} / "
        f"{table['v4_reproduction_scale_difference'].abs().max():.1%}"
    )
    print(
        f"Seed thresholds on the v4 curve of their cell: {table['seed_thresholds_on_cell'].sum()} of {len(table)}"
    )
    print("\nv5 / v4 alert threshold per country (median, min, max):")
    print(
        ratio.groupby(table["country"])
        .agg(["median", "min", "max", "count"])
        .round(2)
        .to_string()
    )
    print(f"\nPlacement: {table['placement'].value_counts().to_dict()}")
    print(
        f"Next to the river in v5: {', '.join(table.loc[table['v5_station_next_to_river'], 'station_code']) or 'none'}"
    )
    print(
        f"Years at the alert threshold in the last {RECENT_YEARS} years, all stations: "
        f"v5 without trend step {table['v5_unadjusted_recent_trigger_years'].sum()}, "
        f"v5 {table['v5_recent_trigger_years'].sum()}"
    )


def _find_v5_river_cell(
    annual_maxima: xr.DataArray, v4_mean_annual_maximum: float
) -> tuple[int, int]:
    """The station's own cell, unless a cell right next to it carries its river in v5.

    That cell has much more flow than the station's own cell, and is closer to v4's flow at the station,
    so a tributary next to a main river stays on the tributary.
    Discharge stands in for upstream area, as the v5 upstream area map is not published yet.
    """
    radius = RIVER_SEARCH_RADIUS_CELLS
    mean_by_cell = annual_maxima.mean("year").to_numpy()
    around = mean_by_cell[
        WINDOW_RADIUS_CELLS - radius : WINDOW_RADIUS_CELLS + radius + 1,
        WINDOW_RADIUS_CELLS - radius : WINDOW_RADIUS_CELLS + radius + 1,
    ]
    with np.errstate(divide="ignore", invalid="ignore"):
        distance_to_v4 = np.abs(np.log(around / v4_mean_annual_maximum))
    candidates = (around >= NEIGHBOURING_RIVER_FACTOR * around[radius, radius]) & (
        distance_to_v4 < distance_to_v4[radius, radius]
    )
    if not candidates.any():
        return WINDOW_RADIUS_CELLS, WINDOW_RADIUS_CELLS
    best_row, best_column = np.unravel_index(
        np.nanargmin(np.where(candidates, distance_to_v4, np.inf)), around.shape
    )
    return (
        WINDOW_RADIUS_CELLS - radius + int(best_row),
        WINDOW_RADIUS_CELLS - radius + int(best_column),
    )


def _by_return_period(prefix: str, thresholds: dict[float, float]) -> TableRow:
    return {
        f"{prefix}_rp{return_period:g}": thresholds[return_period]
        for return_period in RETURN_PERIODS
    }


def _annual_maxima(discharge: xr.DataArray) -> xr.DataArray:
    return discharge.groupby(f"{TIME}.year").max()


def _centre(by_cell: xr.DataArray) -> xr.DataArray:
    return by_cell.isel(row=WINDOW_RADIUS_CELLS, column=WINDOW_RADIUS_CELLS)


def _count_recent_trigger_years(
    annual_maxima: xr.DataArray, trigger_threshold: float
) -> int:
    recent = annual_maxima.sel(year=slice(LAST_YEAR - RECENT_YEARS + 1, LAST_YEAR))
    return int((recent >= trigger_threshold).sum())


if __name__ == "__main__":
    main()
