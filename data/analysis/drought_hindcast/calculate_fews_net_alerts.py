"""Calculate FEWS NET drought alerts per region-season, year and run month.

The value of a run is the share of the region that the latest report before the run
projects in Phase 3 or worse, in the projection that covers most of the season.
"""

import numpy as np
import pandas as pd
from analysis.drought_hindcast.calculate_iod_alerts import (
    calculate_leave_one_out_quantile,
)
from analysis.drought_hindcast.definitions import (
    REGION_SEASONS,
    RUN_MONTHS_BEFORE_SEASON,
    UPPER_TERCILE,
)
from analysis.drought_hindcast.indicator_data import (
    FEWS_NET_ALERTS_FILE,
    FEWS_NET_REGION_PHASES_FILE,
)
from analysis.drought_hindcast.indicator_definitions import (
    FEWS_NET_MAXIMUM_CURRENT_SITUATION_AGE_MONTHS,
    FEWS_NET_MAXIMUM_REPORT_AGE_MONTHS,
    FEWS_NET_MINIMUM_AREA_SHARE,
    FEWS_NET_REPORT_LAG_MONTHS,
    FewsNetAlertRule,
    get_fews_net_alert_column,
)
from analysis.drought_hindcast.prepare_fews_net import CRISIS_OR_WORSE_COLUMN
from analysis.drought_hindcast.prepare_iod import MONTH_FREQUENCY
from analysis.drought_hindcast.study_area import OBSERVED_SEASONS_FILE

CURRENT_SITUATION_SCENARIO = "CS"
REPORT_MONTH_COLUMN = "report_month"
PROJECTION_START_COLUMN = "projection_start_month"
PROJECTION_END_COLUMN = "projection_end_month"
CURRENT_SHARE_COLUMN = f"current_{CRISIS_OR_WORSE_COLUMN}"
PROJECTED_CHANGE_COLUMN = "projected_change"
SHARE_RANK_COLUMN = "share_rank_among_other_years"
CHANGE_RANK_COLUMN = "change_rank_among_other_years"
SHARE_DECIMALS = 4


def main() -> None:
    phases = load_region_phases()
    run_tables: list[pd.DataFrame] = []
    for region_season in REGION_SEASONS:
        region_phases = phases.loc[phases["region_key"] == region_season.region_key]
        for report_lag_months in FEWS_NET_REPORT_LAG_MONTHS:
            for months_until_season_start in range(RUN_MONTHS_BEFORE_SEASON, -1, -1):
                run_alerts = calculate_run_month_alerts(
                    region_phases,
                    region_season.months[0],
                    len(region_season.months),
                    months_until_season_start,
                    report_lag_months,
                )
                run_alerts.insert(0, "region_season", region_season.name)
                run_tables.append(run_alerts)
        print(
            f"{region_season.name}: {region_phases[REPORT_MONTH_COLUMN].nunique()} reports"
        )

    fews_net_alerts = pd.concat(run_tables).merge(
        pd.read_csv(OBSERVED_SEASONS_FILE),
        on=["region_season", "season_year"],
        how="left",
        validate="many_to_one",
    )
    fews_net_alerts.to_csv(FEWS_NET_ALERTS_FILE, index=False)
    print(f"Wrote {len(fews_net_alerts)} rows to {FEWS_NET_ALERTS_FILE}")


def load_region_phases() -> pd.DataFrame:
    """The prepared phase shares, with the months of each report and projection."""
    phases = pd.read_csv(FEWS_NET_REGION_PHASES_FILE)
    for month_column, date_column in {
        REPORT_MONTH_COLUMN: "reporting_date",
        PROJECTION_START_COLUMN: "projection_start",
        PROJECTION_END_COLUMN: "projection_end",
    }.items():
        phases[month_column] = pd.PeriodIndex(phases[date_column], freq=MONTH_FREQUENCY)
    return phases


def calculate_run_month_alerts(
    region_phases: pd.DataFrame,
    first_season_month: int,
    season_month_count: int,
    months_until_season_start: int,
    report_lag_months: int,
) -> pd.DataFrame:
    """One row per season year (the year of the first season month) that has a report."""
    is_current_situation = region_phases["scenario"] == CURRENT_SITUATION_SCENARIO
    current_situations = region_phases.loc[is_current_situation]
    projections = region_phases.loc[~is_current_situation]
    report_months = projections[REPORT_MONTH_COLUMN]
    if report_months.empty:
        return pd.DataFrame()

    rows = []
    # One year beyond the data, for runs ahead of a season that starts next year.
    for season_year in range(report_months.min().year, report_months.max().year + 2):
        season_start = pd.Period(
            year=season_year, month=first_season_month, freq=MONTH_FREQUENCY
        )
        run_month = season_start - months_until_season_start
        is_usable_report = (report_months <= run_month - report_lag_months) & (
            report_months >= run_month - FEWS_NET_MAXIMUM_REPORT_AGE_MONTHS
        )
        if not is_usable_report.any():
            continue
        report_month = report_months[is_usable_report].max()
        projection = select_projection(
            projections.loc[report_months == report_month],
            season_start,
            season_month_count,
        )
        current_share = find_current_share(current_situations, report_month)
        share = projection[CRISIS_OR_WORSE_COLUMN]
        rows.append(
            {
                "season_year": season_year,
                "run_year": run_month.year,
                "run_month": run_month.month,
                "months_until_season_start": months_until_season_start,
                "report_lag_months": report_lag_months,
                REPORT_MONTH_COLUMN: str(report_month),
                "scenario": projection["scenario"],
                PROJECTION_START_COLUMN: str(projection[PROJECTION_START_COLUMN]),
                PROJECTION_END_COLUMN: str(projection[PROJECTION_END_COLUMN]),
                "projection_season_month_count": count_season_months(
                    projection, season_start, season_month_count
                ),
                CRISIS_OR_WORSE_COLUMN: share,
                CURRENT_SHARE_COLUMN: current_share,
                PROJECTED_CHANGE_COLUMN: (
                    None
                    if current_share is None
                    else round(share - current_share, SHARE_DECIMALS)
                ),
            }
        )
    runs = pd.DataFrame(rows)
    if runs.empty:
        return runs

    shares = runs[CRISIS_OR_WORSE_COLUMN].to_numpy()
    changes = runs[PROJECTED_CHANGE_COLUMN].astype(float).to_numpy()
    runs[SHARE_RANK_COLUMN] = calculate_rank_among_others(shares).round(SHARE_DECIMALS)
    runs[CHANGE_RANK_COLUMN] = calculate_rank_among_others(changes).round(
        SHARE_DECIMALS
    )
    # Without any area in Phase 3 or worse there is no alert, also where that is usual.
    runs[get_fews_net_alert_column(FewsNetAlertRule.OWN_TERCILE)] = (shares > 0) & (
        shares >= calculate_own_terciles(shares)
    )
    runs[get_fews_net_alert_column(FewsNetAlertRule.FIXED_SHARE)] = (
        shares >= FEWS_NET_MINIMUM_AREA_SHARE
    )
    # The usual change differs per run month, as food insecurity follows the seasons.
    runs[get_fews_net_alert_column(FewsNetAlertRule.WORSENING)] = (changes > 0) & (
        changes >= calculate_own_terciles(changes)
    )
    return runs


def calculate_rank_among_others(values: np.ndarray) -> np.ndarray:
    """Per value, the share of the other values below it; an equal value counts half.

    It makes regions comparable: 0.5 is the usual level of a region, whatever that is.
    """
    ranks = np.full(len(values), np.nan)
    has_value = ~np.isnan(values)
    known_values = values[has_value]
    if len(known_values) < 2:
        return ranks
    lower_counts = (known_values[:, np.newaxis] > known_values).sum(axis=1)
    equal_counts = (known_values[:, np.newaxis] == known_values).sum(axis=1) - 1
    ranks[has_value] = (lower_counts + equal_counts / 2) / (len(known_values) - 1)
    return ranks


def calculate_own_terciles(values: np.ndarray) -> np.ndarray:
    """Per value, the upper tercile of the other values; none where the value is missing."""
    terciles = np.full(len(values), np.nan)
    has_value = ~np.isnan(values)
    terciles[has_value] = calculate_leave_one_out_quantile(
        values[has_value], UPPER_TERCILE
    )
    return terciles


def select_projection(
    report_projections: pd.DataFrame, season_start: pd.Period, season_month_count: int
) -> pd.Series:
    """The projection of a report that covers most season months.

    With as many months, the earlier projection; without any, the one that reaches furthest.
    """
    season_months_covered = report_projections.apply(
        count_season_months,
        axis="columns",
        season_start=season_start,
        season_month_count=season_month_count,
    )
    if season_months_covered.max() == 0:
        return report_projections.loc[
            report_projections[PROJECTION_END_COLUMN].idxmax()
        ]
    most_covering = report_projections.loc[
        season_months_covered == season_months_covered.max()
    ]
    return most_covering.loc[most_covering[PROJECTION_START_COLUMN].idxmin()]


def count_season_months(
    projection: pd.Series, season_start: pd.Period, season_month_count: int
) -> int:
    season_end = season_start + season_month_count - 1
    first_month = max(projection[PROJECTION_START_COLUMN], season_start)
    last_month = min(projection[PROJECTION_END_COLUMN], season_end)
    return max((last_month - first_month).n + 1, 0)


def find_current_share(
    current_situations: pd.DataFrame, report_month: pd.Period
) -> float | None:
    """Share in Phase 3 or worse in the latest current situation up to the report."""
    months = current_situations[REPORT_MONTH_COLUMN]
    is_usable = (months <= report_month) & (
        months >= report_month - FEWS_NET_MAXIMUM_CURRENT_SITUATION_AGE_MONTHS
    )
    if not is_usable.any():
        return None
    return float(
        current_situations.loc[months[is_usable].idxmax(), CRISIS_OR_WORSE_COLUMN]
    )


if __name__ == "__main__":
    main()
