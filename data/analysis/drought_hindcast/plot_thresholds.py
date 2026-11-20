"""Sweep the share of members that must be dry for an alert, and draw what it does to the
hit rate and the false-alarm ratio."""

import numpy as np
import pandas as pd
from analysis.drought_hindcast.calculate_skill import (
    BOOTSTRAP_SEED,
    calculate_scores,
    load_scorable_cases,
    select_pooled_cases,
    to_booleans,
)
from analysis.drought_hindcast.definitions import get_observed_drought_column
from analysis.drought_hindcast.plot_skill import (
    capitalise,
    DEFAULT_DROUGHT_DEFINITION,
    draw_measures,
    DROUGHT_DEFINITION_LABELS,
    finish_figure,
    POOLED_LABEL,
    style_percent_axis,
)
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.ticker import PercentFormatter

SWEEP_THRESHOLDS = tuple(percent / 100 for percent in range(30, 75, 5))
SWEEP_MONTHS_BEFORE_SEASON = (3, 1, 0)
THRESHOLD_AXIS_LABEL = "Share of members that must be dry for an alert"
THRESHOLD_MEASURE_OFFSET = 0.004
THRESHOLD_PANEL_SIZE_INCHES = (4.2, 4.6)
# Guards the whole number of members against floating-point error in threshold x members.
MEMBER_COUNT_DECIMALS = 6


def main() -> None:
    cases = select_pooled_cases(load_scorable_cases())
    plot_threshold_sweep(cases, capitalise(POOLED_LABEL), "skill_by_threshold")


def plot_threshold_sweep(cases: pd.DataFrame, cases_label: str, file_name: str) -> None:
    """One panel per lead time, with the threshold along the horizontal axis."""
    random_generator = np.random.default_rng(BOOTSTRAP_SEED)
    panel_width, panel_height = THRESHOLD_PANEL_SIZE_INCHES
    figure = Figure(
        figsize=(len(SWEEP_MONTHS_BEFORE_SEASON) * panel_width, panel_height),
        layout="constrained",
    )
    axes = figure.subplots(1, len(SWEEP_MONTHS_BEFORE_SEASON), sharey=True)
    for axis, months_before_season in zip(
        axes, SWEEP_MONTHS_BEFORE_SEASON, strict=True
    ):
        lead_cases = cases.loc[
            cases["months_until_season_start"] == months_before_season
        ]
        _draw_threshold_panel(
            axis,
            score_thresholds(lead_cases, SWEEP_THRESHOLDS, random_generator),
            _format_lead_time(months_before_season),
        )
    finish_figure(
        figure,
        f"{cases_label}; "
        f"{DROUGHT_DEFINITION_LABELS[DEFAULT_DROUGHT_DEFINITION].lower()}",
        file_name,
        x_label=THRESHOLD_AXIS_LABEL,
        shows_partial_seasons=False,
    )


def score_thresholds(
    cases: pd.DataFrame,
    thresholds: tuple[float, ...],
    random_generator: np.random.Generator,
) -> pd.DataFrame:
    """Scores of the region rule per threshold, for cases of one lead time."""
    dry_member_counts = count_dry_members(cases)
    member_counts = cases["member_count"].to_numpy()
    is_drought = to_booleans(
        cases, get_observed_drought_column(DEFAULT_DROUGHT_DEFINITION)
    )
    return pd.DataFrame(
        [
            {
                "threshold": threshold,
                **calculate_scores(
                    is_alert=dry_member_counts
                    >= get_minimum_dry_member_counts(threshold, member_counts),
                    is_drought=is_drought,
                    season_years=cases["season_year"].to_numpy(),
                    random_generator=random_generator,
                ),
            }
            for threshold in thresholds
        ]
    )


def count_dry_members(cases: pd.DataFrame) -> np.ndarray:
    """Whole members behind the stored share, which is rounded."""
    return np.rint(
        cases["probability_below_lower_tercile"].to_numpy()
        * cases["member_count"].to_numpy()
    ).astype(int)


def get_minimum_dry_member_counts(
    threshold: float, member_counts: np.ndarray
) -> np.ndarray:
    return np.ceil(np.round(threshold * member_counts, MEMBER_COUNT_DECIMALS))


def _draw_threshold_panel(axis: Axes, scores: pd.DataFrame, title: str) -> None:
    draw_measures(axis, scores["threshold"], scores, THRESHOLD_MEASURE_OFFSET)
    axis.set_xticks(scores["threshold"])
    axis.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    style_percent_axis(axis, title)


def _format_lead_time(months_before_season: int) -> str:
    if months_before_season == 0:
        return "At the season start"
    month_word = "month" if months_before_season == 1 else "months"
    return f"{months_before_season} {month_word} before the season"


if __name__ == "__main__":
    main()
