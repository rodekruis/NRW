"""Calculate IOD drought alerts per region-season, year and run month, for every source."""

import numpy as np
import pandas as pd
from analysis.drought_hindcast.definitions import (
    RUN_MONTHS_BEFORE_SEASON,
    UPPER_TERCILE,
)
from analysis.drought_hindcast.download_iod import IodSource
from analysis.drought_hindcast.indicator_data import IOD_ALERTS_FILE, IOD_MONTHLY_FILE
from analysis.drought_hindcast.indicator_definitions import (
    get_iod_alert_column,
    get_iod_region_seasons,
    IOD_DROUGHT_PHASES,
    IOD_EVENT_THRESHOLD,
    IOD_INDEX_MONTH_COUNTS,
    IOD_PHASE_SIGNS,
    IodAlertRule,
    IodPhase,
)
from analysis.drought_hindcast.prepare_iod import get_iod_column, MONTH_FREQUENCY
from analysis.drought_hindcast.study_area import OBSERVED_SEASONS_FILE

INDEX_DECIMALS = 3


def main() -> None:
    monthly_index = load_monthly_index()
    run_tables: list[pd.DataFrame] = []
    for region_season in get_iod_region_seasons():
        drought_phase = IOD_DROUGHT_PHASES[region_season.name]
        for source in IodSource:
            for index_month_count in IOD_INDEX_MONTH_COUNTS:
                for months_until_season_start in range(
                    RUN_MONTHS_BEFORE_SEASON, -1, -1
                ):
                    run_alerts = calculate_run_month_alerts(
                        monthly_index[get_iod_column(source)].dropna(),
                        region_season.months[0],
                        drought_phase,
                        months_until_season_start,
                        index_month_count,
                    )
                    run_alerts.insert(0, "region_season", region_season.name)
                    run_alerts.insert(5, "iod_source", source.value)
                    run_alerts.insert(6, "index_month_count", index_month_count)
                    run_alerts.insert(7, "drought_phase", drought_phase.value)
                    run_tables.append(run_alerts)
        print(f"{region_season.name}: drought goes with a {drought_phase} IOD")

    iod_alerts = pd.concat(run_tables).merge(
        pd.read_csv(OBSERVED_SEASONS_FILE),
        on=["region_season", "season_year"],
        how="left",
        validate="many_to_one",
    )
    iod_alerts.to_csv(IOD_ALERTS_FILE, index=False)
    print(f"Wrote {len(iod_alerts)} rows to {IOD_ALERTS_FILE}")


def load_monthly_index() -> pd.DataFrame:
    monthly_index = pd.read_csv(IOD_MONTHLY_FILE, index_col="month")
    monthly_index.index = pd.PeriodIndex(monthly_index.index, freq=MONTH_FREQUENCY)
    return monthly_index


def calculate_run_month_alerts(
    monthly_index: pd.Series,
    first_season_month: int,
    drought_phase: IodPhase,
    months_until_season_start: int,
    index_month_count: int,
) -> pd.DataFrame:
    """One row per season year (the year of the first season month) that has an index.

    The index of a run is the average over the months just before the run month.
    """
    months = pd.period_range(
        monthly_index.index.min(), monthly_index.index.max() + 1, freq=MONTH_FREQUENCY
    )
    index_before_month = (
        monthly_index.reindex(months).rolling(index_month_count).mean().shift(1)
    )
    # One year beyond the data, for runs ahead of a season that starts next year.
    season_years = np.arange(months[0].year, months[-1].year + 2)
    run_months = pd.PeriodIndex(
        [
            pd.Period(year=year, month=first_season_month, freq=MONTH_FREQUENCY)
            - months_until_season_start
            for year in season_years
        ]
    )
    runs = pd.DataFrame(
        {
            "season_year": season_years,
            "run_year": run_months.year,
            "run_month": run_months.month,
            "months_until_season_start": months_until_season_start,
            "iod_index": index_before_month.reindex(run_months).to_numpy(),
        }
    ).dropna(subset="iod_index", ignore_index=True)

    sign = IOD_PHASE_SIGNS[drought_phase]
    index_towards_drought = sign * runs["iod_index"].to_numpy()
    own_terciles = calculate_leave_one_out_quantile(
        index_towards_drought, UPPER_TERCILE
    )
    runs["own_tercile_threshold"] = (sign * own_terciles).round(INDEX_DECIMALS)
    runs[get_iod_alert_column(IodAlertRule.OWN_TERCILE)] = (
        index_towards_drought >= own_terciles
    )
    runs[get_iod_alert_column(IodAlertRule.FIXED_THRESHOLD)] = (
        index_towards_drought >= IOD_EVENT_THRESHOLD
    )
    runs["iod_index"] = runs["iod_index"].round(INDEX_DECIMALS)
    return runs


def calculate_leave_one_out_quantile(values: np.ndarray, quantile: float) -> np.ndarray:
    """Per value, the quantile of all other values; none for a single value."""
    if len(values) < 2:
        return np.full(len(values), np.nan)
    return np.array(
        [
            np.quantile(np.delete(values, position), quantile)
            for position in range(len(values))
        ]
    )


if __name__ == "__main__":
    main()
