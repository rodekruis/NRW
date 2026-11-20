"""Split the forecasts by the highest alert threshold they reach, and count how many in
each band were not followed by a drought. That is the false-alarm ratio of the alerts
that one step down in the threshold adds."""

import numpy as np
import pandas as pd
from analysis.drought_hindcast.calculate_skill import (
    load_scorable_cases,
    SCORE_DECIMALS,
    select_pooled_cases,
    to_booleans,
)
from analysis.drought_hindcast.definitions import (
    DEFAULT_PROBABILITY_THRESHOLD,
    get_observed_drought_column,
    PROBABILITY_THRESHOLDS,
)
from analysis.drought_hindcast.indicator_charts import add_legend, create_panels
from analysis.drought_hindcast.indicator_data import THRESHOLD_STEPS_FILE
from analysis.drought_hindcast.plot_skill import (
    capitalise,
    DEFAULT_DROUGHT_DEFINITION,
    DROUGHT_DEFINITION_LABELS,
    FALSE_ALARM_RATIO_COLOUR,
    GRID_COLOUR,
    NEUTRAL_COLOUR,
    NO_SKILL_LINE_STYLE,
    POOLED_LABEL,
    save_figure,
    style_percent_axis,
)
from analysis.drought_hindcast.plot_thresholds import (
    count_dry_members,
    get_minimum_dry_member_counts,
)
from matplotlib.axes import Axes
from matplotlib.lines import Line2D

STEP_MONTHS_BEFORE_SEASON = (1, 0)
STEP_FIGURE_WIDTH_INCHES = 10.5
STEP_PANEL_HEIGHT_INCHES = 3.3
ADDED_BY_ONE_STEP_DOWN_OPACITY = 0.45
BAR_WIDTH = 0.7
BAR_LABEL_OFFSET = 0.02
# Keeps the line of the level without skill from running through a label.
BAR_LABEL_BACKGROUND = {"facecolor": "white", "edgecolor": "none", "pad": 1}
BAND_AXIS_LABEL = "Share of members that are dry"


def main() -> None:
    bands = summarise_threshold_bands(select_pooled_cases(load_scorable_cases()))
    bands.to_csv(THRESHOLD_STEPS_FILE, index=False)
    print(f"Wrote {len(bands)} rows to {THRESHOLD_STEPS_FILE}")
    _plot_threshold_steps(bands)


def summarise_threshold_bands(cases: pd.DataFrame) -> pd.DataFrame:
    """Per lead time and band between two thresholds: the forecasts in it, and how many
    were not followed by a drought. Bands run from the highest threshold down.
    """
    thresholds = sorted(PROBABILITY_THRESHOLDS)
    is_drought = to_booleans(
        cases, get_observed_drought_column(DEFAULT_DROUGHT_DEFINITION)
    )
    thresholds_reached = count_thresholds_reached(cases, thresholds)
    rows = []
    for months_before_season in sorted(
        cases["months_until_season_start"].unique(), reverse=True
    ):
        is_lead_time = (
            cases["months_until_season_start"] == months_before_season
        ).to_numpy()
        for reached_count in range(len(thresholds), -1, -1):
            is_in_band = is_lead_time & (thresholds_reached == reached_count)
            forecast_count = int(is_in_band.sum())
            false_alarm_count = int((is_in_band & ~is_drought).sum())
            rows.append(
                {
                    "months_until_season_start": months_before_season,
                    "lower_threshold": (
                        thresholds[reached_count - 1] if reached_count > 0 else None
                    ),
                    "upper_threshold": (
                        thresholds[reached_count]
                        if reached_count < len(thresholds)
                        else None
                    ),
                    "forecast_count": forecast_count,
                    "false_alarm_count": false_alarm_count,
                    "false_alarm_ratio": (
                        round(false_alarm_count / forecast_count, SCORE_DECIMALS)
                        if forecast_count > 0
                        else None
                    ),
                    "false_alarm_ratio_without_skill": round(
                        float((~is_drought[is_lead_time]).mean()), SCORE_DECIMALS
                    ),
                }
            )
    return pd.DataFrame(rows)


def count_thresholds_reached(
    cases: pd.DataFrame, thresholds: list[float]
) -> np.ndarray:
    dry_member_counts = count_dry_members(cases)
    member_counts = cases["member_count"].to_numpy()
    return np.sum(
        [
            dry_member_counts >= get_minimum_dry_member_counts(threshold, member_counts)
            for threshold in thresholds
        ],
        axis=0,
    )


def _plot_threshold_steps(bands: pd.DataFrame) -> None:
    """One bar per band: the false-alarm ratio of its forecasts as alerts, against the
    ratio of alerts unrelated to droughts.
    """
    figure, axes = create_panels(
        row_count=1,
        column_count=len(STEP_MONTHS_BEFORE_SEASON),
        shares_lead_times=False,
        figure_width_inches=STEP_FIGURE_WIDTH_INCHES,
        panel_height_inches=STEP_PANEL_HEIGHT_INCHES,
    )
    for axis, months_before_season in zip(
        axes[0], STEP_MONTHS_BEFORE_SEASON, strict=True
    ):
        _draw_bands(
            axis,
            bands.loc[bands["months_until_season_start"] == months_before_season],
            (
                "At the season start"
                if months_before_season == 0
                else f"{months_before_season} month before the season"
            ),
        )
    axes[0][0].set_ylabel("False-alarm ratio in the band")
    one_step_down = max(
        threshold
        for threshold in PROBABILITY_THRESHOLDS
        if threshold < DEFAULT_PROBABILITY_THRESHOLD
    )
    add_legend(
        figure,
        [
            _create_legend_square(1, f"Alert at {DEFAULT_PROBABILITY_THRESHOLD:.0%}"),
            _create_legend_square(
                ADDED_BY_ONE_STEP_DOWN_OPACITY,
                f"Alerts added by lowering to {one_step_down:.0%}",
            ),
            Line2D(
                [],
                [],
                linestyle="",
                marker="s",
                color=GRID_COLOUR,
                label=f"No alert at {one_step_down:.0%}: seasons without a drought",
            ),
            Line2D(
                [],
                [],
                color=NEUTRAL_COLOUR,
                linestyle=NO_SKILL_LINE_STYLE,
                label="Level without skill",
            ),
        ],
        f"{capitalise(POOLED_LABEL)}; "
        f"{DROUGHT_DEFINITION_LABELS[DEFAULT_DROUGHT_DEFINITION].lower()}",
        x_label=BAND_AXIS_LABEL,
    )
    save_figure(figure, "threshold_steps")


def _draw_bands(axis: Axes, bands: pd.DataFrame, title: str) -> None:
    positions = range(len(bands))
    for position, (_, band) in zip(positions, bands.iterrows(), strict=True):
        colour, opacity = _get_band_style(band)
        axis.bar(
            position,
            band["false_alarm_ratio"],
            width=BAR_WIDTH,
            color=colour,
            alpha=opacity,
        )
        axis.text(
            position,
            band["false_alarm_ratio"] + BAR_LABEL_OFFSET,
            f"{band['false_alarm_ratio']:.0%}\n"
            f"{band['false_alarm_count']:.0f} of {band['forecast_count']:.0f}",
            horizontalalignment="center",
            verticalalignment="bottom",
            fontsize="small",
            bbox=BAR_LABEL_BACKGROUND,
            zorder=3,
        )
    axis.axhline(
        bands["false_alarm_ratio_without_skill"].iloc[0],
        color=NEUTRAL_COLOUR,
        linestyle=NO_SKILL_LINE_STYLE,
    )
    axis.set_xticks(
        positions,
        [
            format_band(band["lower_threshold"], band["upper_threshold"])
            for _, band in bands.iterrows()
        ],
    )
    style_percent_axis(axis, title)


def _get_band_style(band: pd.Series) -> tuple[str, float]:
    if band["lower_threshold"] >= DEFAULT_PROBABILITY_THRESHOLD:
        return FALSE_ALARM_RATIO_COLOUR, 1
    if band["upper_threshold"] == DEFAULT_PROBABILITY_THRESHOLD:
        return FALSE_ALARM_RATIO_COLOUR, ADDED_BY_ONE_STEP_DOWN_OPACITY
    return GRID_COLOUR, 1


def format_band(lower_threshold: float, upper_threshold: float) -> str:
    if pd.isna(lower_threshold):
        return f"Below {upper_threshold:.0%}"
    if pd.isna(upper_threshold):
        return f"{lower_threshold:.0%} or more"
    return f"{lower_threshold * 100:.0f}–{upper_threshold:.0%}"


def _create_legend_square(opacity: float, label: str) -> Line2D:
    return Line2D(
        [],
        [],
        linestyle="",
        marker="s",
        color=FALSE_ALARM_RATIO_COLOUR,
        alpha=opacity,
        label=label,
    )


if __name__ == "__main__":
    main()
