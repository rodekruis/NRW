"""Compare GloFAS v5 flood thresholds, computed from the v5 reanalysis with ECMWF's method, with today's v4 thresholds."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
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
RETURN_PERIODS = [1.5, 2.0, 5.0, 10.0, 20.0]
# The period of ECMWF's published v4 thresholds, see https://confluence.ecmwf.int/spaces/CEMS/pages/715612883/GloFAS+flood+threshold+generation
V4_PUBLISHED_FIRST_YEAR = 1979
V4_PUBLISHED_LAST_YEAR = 2022
V5_FIRST_YEAR = 1980
TREND_REFERENCE_YEAR = LAST_YEAR
RECENT_YEARS = 10
# A v5 cell whose typical annual maximum is outside this factor of v4's suggests the station is on another river cell.
OTHER_RIVER_CELL_FACTOR = 2.0
# A neighbouring v5 cell this close to v4's typical annual maximum is a likely match for the station's river.
MATCHING_CELL_FACTOR = 1.25


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
    table.to_csv(RESULTS_DIRECTORY / "station_threshold_comparison.csv", index=False)
    plot_threshold_ratios(table, RESULTS_DIRECTORY / "threshold_ratio_by_station.png")
    print_summary(table)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--download-directory", type=Path, default=DEFAULT_DOWNLOAD_DIRECTORY
    )
    return parser.parse_args()


def compare_station(
    station: Station,
    v5: xr.Dataset,
    v4_curves: xr.Dataset,
    v4: xr.Dataset | None,
) -> TableRow:
    v5_annual_maxima = _annual_maxima(v5[DISCHARGE]).sel(
        year=slice(V5_FIRST_YEAR, LAST_YEAR)
    )
    v5_centre = _centre(v5_annual_maxima)

    published_curve = v4_curves.sel(
        {LATITUDE: station.latitude, LONGITUDE: station.longitude}, method="nearest"
    )
    published_location = float(published_curve[LOCATION])
    published_scale = float(published_curve[SCALE])
    v4_thresholds = {
        return_period: gumbel_threshold(
            return_period, published_location, published_scale
        )
        for return_period in RETURN_PERIODS
    }

    trend = adjust_for_trend(
        v5_centre.to_numpy(), v5_centre["year"].to_numpy(), TREND_REFERENCE_YEAR
    )
    v5_unadjusted = fit_gumbel(v5_centre.to_numpy())
    v5_adjusted = fit_gumbel(trend.adjusted_annual_maxima)
    v5_unadjusted_thresholds = {
        return_period: gumbel_threshold(return_period, *v5_unadjusted)
        for return_period in RETURN_PERIODS
    }
    v5_thresholds = {
        return_period: gumbel_threshold(return_period, *v5_adjusted)
        for return_period in RETURN_PERIODS
    }

    # The mean of the fitted v4 Gumbel distribution, so no v4 reanalysis is needed.
    v4_mean_annual_maximum = published_location + np.euler_gamma * published_scale
    v5_to_v4_by_cell = v5_annual_maxima.mean("year") / v4_mean_annual_maximum
    distance_by_cell = np.abs(np.log(v5_to_v4_by_cell.to_numpy()))
    best_row, best_column = np.unravel_index(
        np.nanargmin(distance_by_cell), distance_by_cell.shape
    )
    centre_ratio = float(_centre(v5_to_v4_by_cell))
    best_ratio = float(v5_to_v4_by_cell[best_row, best_column])

    comparison: TableRow = {
        "country": station.country,
        "station_code": station.code,
        "station_name": station.name,
        "seed_thresholds_match_v4_curve": all(
            np.isclose(
                station.thresholds[return_period],
                v4_thresholds[return_period],
                rtol=0.01,
            )
            for return_period in RETURN_PERIODS
        ),
        "v5_trend_per_decade_relative": 10
        * trend.slope_per_year
        / float(v5_centre.mean()),
        "v5_trend_r_squared": trend.r_squared,
        "v5_to_v4_mean_annual_maximum": centre_ratio,
        "best_matching_v5_cell_offset": f"{best_row - WINDOW_RADIUS_CELLS:+d},{best_column - WINDOW_RADIUS_CELLS:+d}",
        "best_matching_v5_to_v4_mean_annual_maximum": best_ratio,
        "possible_other_river_cell": (
            not 1 / OTHER_RIVER_CELL_FACTOR <= centre_ratio <= OTHER_RIVER_CELL_FACTOR
            and 1 / MATCHING_CELL_FACTOR <= best_ratio <= MATCHING_CELL_FACTOR
        ),
        "v5_unadjusted_recent_trigger_years": _count_recent_trigger_years(
            v5_centre, v5_unadjusted_thresholds[MINIMUM_RETURN_PERIOD_YEARS]
        ),
        "v5_recent_trigger_years": _count_recent_trigger_years(
            v5_centre, v5_thresholds[MINIMUM_RETURN_PERIOD_YEARS]
        ),
        # Only where the v4 reanalysis is downloaded.
        "v4_reproduction_location_difference": np.nan,
        "v4_reproduction_scale_difference": np.nan,
        "v4_recent_trigger_years": np.nan,
        **{
            f"v4_rp{return_period:g}": value
            for return_period, value in v4_thresholds.items()
        },
        **{
            f"v5_unadjusted_rp{return_period:g}": value
            for return_period, value in v5_unadjusted_thresholds.items()
        },
        **{
            f"v5_rp{return_period:g}": value
            for return_period, value in v5_thresholds.items()
        },
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
    return comparison


def fit_gumbel(annual_maxima: np.ndarray) -> tuple[float, float]:
    """Location and scale from the first two sample L-moments, as in ECMWF's lisflood-utilities."""
    sorted_maxima = np.sort(annual_maxima)
    count = len(sorted_maxima)
    first_probability_weighted_moment = (
        np.sum(np.arange(count) / (count - 1) * sorted_maxima) / count
    )
    first_l_moment = float(np.mean(sorted_maxima))
    second_l_moment = 2 * first_probability_weighted_moment - first_l_moment
    scale = second_l_moment / np.log(2)
    location = first_l_moment - np.euler_gamma * scale
    return location, scale


def gumbel_threshold(return_period: float, location: float, scale: float) -> float:
    return location - scale * np.log(np.log(return_period / (return_period - 1)))


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


def plot_threshold_ratios(table: pd.DataFrame, output_path: Path) -> None:
    trigger = f"rp{MINIMUM_RETURN_PERIOD_YEARS:g}"
    ordered = table.assign(
        adjusted_ratio=table[f"v5_{trigger}"] / table[f"v4_{trigger}"],
        unadjusted_ratio=table[f"v5_unadjusted_{trigger}"] / table[f"v4_{trigger}"],
    ).sort_values(["country", "adjusted_ratio"])
    positions = np.arange(len(ordered))

    figure, axis = plt.subplots(figsize=(max(8, len(ordered) * 0.18), 5))
    axis.scatter(
        positions,
        ordered["unadjusted_ratio"],
        marker="x",
        color="grey",
        label="v5 without trend step",
    )
    axis.scatter(
        positions,
        ordered["adjusted_ratio"],
        color="tab:blue",
        label="v5 (with trend step)",
    )
    axis.axhline(1, color="black", linewidth=0.8)
    axis.set_yscale("log")
    axis.set_xticks(
        positions,
        ordered["country"] + " " + ordered["station_code"],
        rotation=90,
        fontsize=6,
    )
    axis.set_ylabel(f"v5 / v4 {MINIMUM_RETURN_PERIOD_YEARS:g}-year threshold (trigger)")
    axis.legend()
    figure.tight_layout()
    figure.savefig(output_path, dpi=150)
    plt.close(figure)


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
        f"Seed thresholds on the v4 curve of their cell: {table['seed_thresholds_match_v4_curve'].sum()} of {len(table)}"
    )
    print("\nv5 / v4 trigger threshold per country (median, min, max):")
    print(
        ratio.groupby(table["country"])
        .agg(["median", "min", "max", "count"])
        .round(2)
        .to_string()
    )
    print(
        f"\nPossibly on another river cell in v5: {', '.join(table.loc[table['possible_other_river_cell'], 'station_code']) or 'none'}"
    )
    print(
        f"Trigger years in the last {RECENT_YEARS} years, all stations: "
        f"v5 without trend step {table['v5_unadjusted_recent_trigger_years'].sum()}, "
        f"v5 {table['v5_recent_trigger_years'].sum()}"
    )


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
