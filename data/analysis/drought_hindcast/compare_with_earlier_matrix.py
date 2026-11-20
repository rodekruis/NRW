"""Set the earlier 2x2 matrix (IBF v1 alerts against reported droughts, 2025-26) next to
this analysis, changing one thing at a time: the alert rule, the drought definition, the
years."""

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
import pandas as pd
from analysis.drought_hindcast.calculate_skill import (
    ALERT_COLUMN_BY_RULE,
    AREA_RULE_NAME,
    load_scorable_cases,
    select_pooled_cases,
    to_booleans,
)
from analysis.drought_hindcast.definitions import get_observed_drought_column
from analysis.drought_hindcast.plot_skill import (
    DEFAULT_DROUGHT_DEFINITION,
    DEFAULT_RULE,
    FALSE_ALARM_RATIO_COLOUR,
    HIT_RATE_COLOUR,
    POOLED_LABEL,
    RULE_LABELS,
    save_figure,
)
from analysis.drought_hindcast.study_area import (
    EARLIER_MATRIX_CASES_FILE,
    EARLIER_MATRIX_CELLS_FILE,
    FIRST_YEAR,
)
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle


class AlertTiming(StrEnum):
    """Which of the forecasts issued before a season decide whether it had an alert."""

    ONE_MONTH_BEFORE = "one_month_before"
    ANY_LEAD_TIME = "any_lead_time"


class Outcome(StrEnum):
    HIT = "hit"
    FALSE_ALARM = "false alarm"
    MISS = "miss"
    CORRECT_NEGATIVE = "correct negative"


@dataclass(frozen=True)
class OutcomeCounts:
    hit: int
    false_alarm: int
    miss: int
    correct_negative: int

    @property
    def drought_count(self) -> int:
        return self.hit + self.miss

    @property
    def alert_count(self) -> int:
        return self.hit + self.false_alarm

    @property
    def case_count(self) -> int:
        return self.alert_count + self.miss + self.correct_negative


ONE_MONTH_BEFORE_SEASON = 1
SEASON_KEYS = ["region_season", "season_year"]
CELL_SEASON_KEYS = ["our_region_season", "our_season_year"]
RULE_SHORT_LABELS = {
    **{
        rule_name: f"Region-average rule at {rule_name.split('_')[-1].replace('0.', '')}0%"
        for rule_name in ALERT_COLUMN_BY_RULE
        if rule_name != AREA_RULE_NAME
    },
    AREA_RULE_NAME: "Grid-cell rule",
}
TIMING_LABELS = {
    AlertTiming.ONE_MONTH_BEFORE: "one month before",
    AlertTiming.ANY_LEAD_TIME: "any lead time",
}
EARLIER_MATRIX_TITLE = "IBF v1 alerts as posted"
REPORTED_DROUGHTS_LABEL = "reported droughts"
OBSERVED_DROUGHTS_LABEL = "CHIRPS droughts"

MATRIX_PANEL_SIZE_INCHES = (2.9, 3.3)
MATRIX_COUNT_FONT_SIZE = 20
MATRIX_RATIO_FONT_SIZE = 8.5
NEITHER_COLOUR = "#e5e7eb"
DARK_TEXT_COLOUR = "#111827"
# (column, row) of each outcome in a panel: droughts left, alerts on top.
OUTCOME_POSITIONS = {
    Outcome.HIT: (0, 1),
    Outcome.FALSE_ALARM: (1, 1),
    Outcome.MISS: (0, 0),
    Outcome.CORRECT_NEGATIVE: (1, 0),
}
OUTCOME_STYLES = {
    Outcome.HIT: (HIT_RATE_COLOUR, HIT_RATE_COLOUR, "white", "hits"),
    Outcome.FALSE_ALARM: (
        FALSE_ALARM_RATIO_COLOUR,
        FALSE_ALARM_RATIO_COLOUR,
        "white",
        "false alarms",
    ),
    Outcome.MISS: ("white", HIT_RATE_COLOUR, HIT_RATE_COLOUR, "misses"),
    Outcome.CORRECT_NEGATIVE: (
        NEITHER_COLOUR,
        NEITHER_COLOUR,
        DARK_TEXT_COLOUR,
        "neither",
    ),
}


def main() -> None:
    cells = pd.read_csv(EARLIER_MATRIX_CELLS_FILE)
    cases = load_scorable_cases()
    seasons = summarise_seasons(cases)
    cell_cases = _join_cells_with_seasons(cells, seasons)
    cell_cases.to_csv(EARLIER_MATRIX_CASES_FILE, index=False)
    print(f"Wrote {len(cell_cases)} rows to {EARLIER_MATRIX_CASES_FILE}")

    forecasts = cell_cases.loc[cell_cases["counts_once"]]
    pooled_seasons = summarise_seasons(select_pooled_cases(cases))
    earlier_counts = _count_labelled_outcomes(cells["earlier_outcome"])

    _print_agreement_with_earlier_matrix(cell_cases)
    _plot_earlier_matrix(earlier_counts)
    _plot_one_change_each(cell_cases, earlier_counts)
    _plot_alert_timing(pooled_seasons)
    _plot_towards_all_years(cell_cases, forecasts, pooled_seasons)
    _plot_all_years_by_threshold(pooled_seasons)


def summarise_seasons(cases: pd.DataFrame) -> pd.DataFrame:
    """One row per region-season and season year: did each rule alert, under each timing."""
    cases = cases.sort_values("months_until_season_start", ascending=False)
    is_one_month_before = (
        cases["months_until_season_start"] == ONE_MONTH_BEFORE_SEASON
    ).to_numpy()
    alerts = cases[SEASON_KEYS].copy()
    for rule_name, alert_column in ALERT_COLUMN_BY_RULE.items():
        is_alert = to_booleans(cases, alert_column)
        alerts[get_alert_column(rule_name, AlertTiming.ANY_LEAD_TIME)] = is_alert
        alerts[get_alert_column(rule_name, AlertTiming.ONE_MONTH_BEFORE)] = (
            is_alert & is_one_month_before
        )
    alerts["observed_drought"] = to_booleans(
        cases, get_observed_drought_column(DEFAULT_DROUGHT_DEFINITION)
    )
    seasons = alerts.groupby(SEASON_KEYS, sort=False).any()

    grouped_cases = cases.groupby(SEASON_KEYS, sort=False)
    for column, name in (
        ("probability_below_lower_tercile", "shares_of_members_dry"),
        ("area_share_in_drought_extent", "area_shares_dry"),
    ):
        seasons[f"{name}_from_first_to_last_forecast"] = grouped_cases[column].agg(
            lambda shares: " ".join(f"{share:.2f}" for share in shares)
        )
    seasons["observed_rainfall_mm"] = grouped_cases["observed_rainfall_mm"].first()
    seasons["observed_rank_from_driest"] = (
        seasons.groupby("region_season")["observed_rainfall_mm"]
        .rank(method="min")
        .astype(int)
    )
    seasons["observed_season_count"] = seasons.groupby("region_season")[
        "observed_rainfall_mm"
    ].transform("count")
    return seasons.reset_index()


def get_alert_column(rule_name: str, timing: AlertTiming) -> str:
    return f"alert_{rule_name}_{timing.value}"


def _join_cells_with_seasons(
    cells: pd.DataFrame, seasons: pd.DataFrame
) -> pd.DataFrame:
    """Each cell of the earlier matrix with the forecast and observed season it maps to."""
    cell_cases = cells.merge(
        seasons.rename(columns=dict(zip(SEASON_KEYS, CELL_SEASON_KEYS, strict=True))),
        on=CELL_SEASON_KEYS,
        how="left",
    )
    has_forecast = cell_cases["our_region_season"].notna()
    # Two cells can share one forecast, which then counts once against observed rainfall.
    cell_cases["counts_once"] = has_forecast & ~cell_cases.duplicated(CELL_SEASON_KEYS)
    for rule_name in ALERT_COLUMN_BY_RULE:
        for timing in AlertTiming:
            alert_column = get_alert_column(rule_name, timing)
            # A cell without a forecast (not one of our seasons) has no alert.
            cell_cases[alert_column] = cell_cases[alert_column].eq(True)
            cell_cases[f"outcome_{rule_name}_{timing.value}"] = classify_outcomes(
                cell_cases[alert_column].to_numpy(),
                cell_cases["reported_drought"].to_numpy(),
            )
    return cell_cases


def classify_outcomes(is_alert: np.ndarray, is_drought: np.ndarray) -> list[str]:
    return [
        (
            (Outcome.HIT if drought else Outcome.FALSE_ALARM)
            if alert
            else (Outcome.MISS if drought else Outcome.CORRECT_NEGATIVE)
        ).value
        for alert, drought in zip(is_alert, is_drought, strict=True)
    ]


def count_outcomes(is_alert: np.ndarray, is_drought: np.ndarray) -> OutcomeCounts:
    return _count_labelled_outcomes(pd.Series(classify_outcomes(is_alert, is_drought)))


def _count_labelled_outcomes(outcomes: pd.Series) -> OutcomeCounts:
    counts = outcomes.value_counts()
    return OutcomeCounts(
        hit=int(counts.get(Outcome.HIT.value, 0)),
        false_alarm=int(counts.get(Outcome.FALSE_ALARM.value, 0)),
        miss=int(counts.get(Outcome.MISS.value, 0)),
        correct_negative=int(counts.get(Outcome.CORRECT_NEGATIVE.value, 0)),
    )


def _count(
    cases: pd.DataFrame, rule_name: str, timing: AlertTiming, drought_column: str
) -> OutcomeCounts:
    return count_outcomes(
        cases[get_alert_column(rule_name, timing)].to_numpy(dtype=bool),
        cases[drought_column].to_numpy(dtype=bool),
    )


def _plot_earlier_matrix(earlier_counts: OutcomeCounts) -> None:
    figure, axes = _create_matrix_figure(1, 1)
    _draw_matrix_panel(
        axes[0, 0],
        earlier_counts,
        EARLIER_MATRIX_TITLE,
        f"{earlier_counts.case_count} cases, {REPORTED_DROUGHTS_LABEL}",
    )
    save_figure(figure, "matrix_earlier")


def _print_agreement_with_earlier_matrix(cell_cases: pd.DataFrame) -> None:
    """In how many cells each of our versions has an alert where the earlier matrix has one."""
    # As counted in the earlier matrix: an alert that was withdrawn later is no alert there.
    is_earlier_alert = cell_cases["earlier_outcome"].isin(
        [Outcome.HIT.value, Outcome.FALSE_ALARM.value]
    )
    print(
        f"The earlier matrix has an alert in {is_earlier_alert.sum()} of "
        f"{len(cell_cases)} cases. Cases with the same alert or no alert:"
    )
    for rule_name in (AREA_RULE_NAME, DEFAULT_RULE):
        for timing in AlertTiming:
            is_alert = cell_cases[get_alert_column(rule_name, timing)]
            print(
                f"- {RULE_SHORT_LABELS[rule_name]}, {TIMING_LABELS[timing]}: "
                f"{(is_alert == is_earlier_alert).sum()}"
            )


def _plot_one_change_each(
    cell_cases: pd.DataFrame, earlier_counts: OutcomeCounts
) -> None:
    """The earlier matrix, our closest version of it, and that version with one change."""
    scored_on = f"{len(cell_cases)} cases, {REPORTED_DROUGHTS_LABEL}"
    panels = [
        (EARLIER_MATRIX_TITLE, earlier_counts),
        (
            "Closest on paper: grid-cell\nrule, any lead time",
            _count(
                cell_cases,
                AREA_RULE_NAME,
                AlertTiming.ANY_LEAD_TIME,
                "reported_drought",
            ),
        ),
        (
            "Rule changed: region-average\nrule at 40%, any lead time",
            _count(
                cell_cases, DEFAULT_RULE, AlertTiming.ANY_LEAD_TIME, "reported_drought"
            ),
        ),
        (
            "Timing changed: grid-cell\nrule, one month before",
            _count(
                cell_cases,
                AREA_RULE_NAME,
                AlertTiming.ONE_MONTH_BEFORE,
                "reported_drought",
            ),
        ),
    ]
    figure, axes = _create_matrix_figure(1, len(panels))
    for axis, (title, counts) in zip(axes[0], panels, strict=True):
        _draw_matrix_panel(axis, counts, title, scored_on)
    save_figure(figure, "matrix_one_change_each")


def _plot_alert_timing(pooled_seasons: pd.DataFrame) -> None:
    """All years under the default rule: an alert at any lead time, or one month before."""
    scored_on = (
        f"{len(pooled_seasons)} seasons since {FIRST_YEAR},\n{OBSERVED_DROUGHTS_LABEL}"
    )
    figure, axes = _create_matrix_figure(len(AlertTiming), 1)
    for axis, timing in zip(
        axes[:, 0],
        (AlertTiming.ANY_LEAD_TIME, AlertTiming.ONE_MONTH_BEFORE),
        strict=True,
    ):
        _draw_matrix_panel(
            axis,
            _count(pooled_seasons, DEFAULT_RULE, timing, "observed_drought"),
            f"Alert: {TIMING_LABELS[timing]}",
            scored_on,
        )
    save_figure(figure, "matrix_alert_timing")


def _plot_towards_all_years(
    cell_cases: pd.DataFrame, forecasts: pd.DataFrame, pooled_seasons: pd.DataFrame
) -> None:
    """From the cells of the earlier matrix to every scored season, under one definition."""
    panels = [
        (
            "1. The cases of the\nearlier matrix",
            cell_cases,
            "reported_drought",
            f"{len(cell_cases)} cases, {REPORTED_DROUGHTS_LABEL}",
        ),
        (
            "2. Same seasons, drought\nfrom observed rainfall",
            forecasts,
            "observed_drought",
            f"{len(forecasts)} seasons, {OBSERVED_DROUGHTS_LABEL}",
        ),
        (
            f"3. All seasons since {FIRST_YEAR},\n{POOLED_LABEL}",
            pooled_seasons,
            "observed_drought",
            f"{len(pooled_seasons)} seasons, {OBSERVED_DROUGHTS_LABEL}",
        ),
    ]
    figure, axes = _create_matrix_figure(1, len(panels))
    for axis, (title, cases, drought_column, scored_on) in zip(
        axes[0], panels, strict=True
    ):
        _draw_matrix_panel(
            axis,
            _count(cases, DEFAULT_RULE, AlertTiming.ONE_MONTH_BEFORE, drought_column),
            title,
            scored_on,
        )
    save_figure(figure, "matrix_towards_all_years")


def _plot_all_years_by_threshold(pooled_seasons: pd.DataFrame) -> None:
    """All years under the region rule at each threshold, one month before the season."""
    scored_on = f"{len(pooled_seasons)} seasons, {OBSERVED_DROUGHTS_LABEL}"
    figure, axes = _create_matrix_figure(1, len(RULE_LABELS))
    for axis, (rule_name, rule_label) in zip(axes[0], RULE_LABELS.items(), strict=True):
        _draw_matrix_panel(
            axis,
            _count(
                pooled_seasons,
                rule_name,
                AlertTiming.ONE_MONTH_BEFORE,
                "observed_drought",
            ),
            rule_label.replace(" of members", "\nof members"),
            scored_on,
        )
    save_figure(figure, "matrix_all_years_by_threshold")


def _create_matrix_figure(
    row_count: int, column_count: int
) -> tuple[Figure, np.ndarray]:
    panel_width, panel_height = MATRIX_PANEL_SIZE_INCHES
    figure = Figure(
        figsize=(column_count * panel_width, row_count * panel_height),
        layout="constrained",
    )
    return figure, figure.subplots(row_count, column_count, squeeze=False)


def _draw_matrix_panel(
    axis: Axes, counts: OutcomeCounts, title: str, scored_on: str
) -> None:
    """The recurring 2x2 matrix: droughts in the left column, alerts in the top row."""
    count_by_outcome = {
        Outcome.HIT: counts.hit,
        Outcome.FALSE_ALARM: counts.false_alarm,
        Outcome.MISS: counts.miss,
        Outcome.CORRECT_NEGATIVE: counts.correct_negative,
    }
    ratio_by_outcome = {
        Outcome.HIT: f"hit rate {_format_share(counts.hit, counts.drought_count)}",
        # Reads on from the label of the cell: "false alarms", "ratio 18%".
        Outcome.FALSE_ALARM: (
            f"ratio {_format_share(counts.false_alarm, counts.alert_count)}"
        ),
    }
    for outcome, (column, row) in OUTCOME_POSITIONS.items():
        face_colour, edge_colour, text_colour, label = OUTCOME_STYLES[outcome]
        axis.add_patch(
            Rectangle(
                (column + 0.04, row + 0.04),
                0.92,
                0.92,
                facecolor=face_colour,
                edgecolor=edge_colour,
                linewidth=1.5,
            )
        )
        axis.text(
            column + 0.5,
            row + 0.64,
            str(count_by_outcome[outcome]),
            horizontalalignment="center",
            verticalalignment="center",
            fontsize=MATRIX_COUNT_FONT_SIZE,
            fontweight="bold",
            color=text_colour,
        )
        axis.text(
            column + 0.5,
            row + 0.36,
            label,
            horizontalalignment="center",
            verticalalignment="center",
            fontsize="small",
            color=text_colour,
        )
        if outcome in ratio_by_outcome:
            axis.text(
                column + 0.5,
                row + 0.15,
                ratio_by_outcome[outcome],
                horizontalalignment="center",
                verticalalignment="center",
                fontsize=MATRIX_RATIO_FONT_SIZE,
                fontweight="bold",
                color=text_colour,
            )
    axis.set_xlim(0, 2)
    axis.set_ylim(0, 2)
    axis.set_aspect("equal")
    axis.set_xticks([0.5, 1.5], ["Drought", "No drought"])
    axis.set_yticks([0.5, 1.5], ["No alert", "Alert"], rotation=90, va="center")
    axis.xaxis.tick_top()
    axis.tick_params(length=0)
    axis.spines[:].set_visible(False)
    axis.set_title(title, loc="left", fontsize="medium", fontweight="bold")
    axis.set_xlabel(
        f"{scored_on}\n"
        # What alerts unrelated to droughts would score: see draw_measures in plot_skill.
        f"Without skill: hit rate {counts.alert_count / counts.case_count:.0%},\n"
        f"false-alarm ratio {1 - counts.drought_count / counts.case_count:.0%}",
        color=DARK_TEXT_COLOUR,
        loc="left",
    )


def _format_share(count: int, total: int) -> str:
    return f"{count / total:.0%}" if total > 0 else "not defined"


if __name__ == "__main__":
    main()
