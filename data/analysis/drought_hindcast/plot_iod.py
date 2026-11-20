"""Draw the skill of the IOD indicator, next to SEAS5 and combined with it."""

import pandas as pd
from analysis.drought_hindcast.calculate_iod_skill import POOLED_IOD_REGION_SEASONS
from analysis.drought_hindcast.combine_indicators import Combination, SEAS5_THRESHOLDS
from analysis.drought_hindcast.compare_with_skill_review import (
    get_measured_level,
    INCLUDE_MINIMUM_ROC_AREA,
    READINESS_MINIMUM_ROC_AREA,
    SkillLevel,
)
from analysis.drought_hindcast.definitions import RegionSeason
from analysis.drought_hindcast.indicator_charts import (
    add_legend,
    create_panels,
    SEAS5_COLOUR,
    set_lead_time_axis,
)
from analysis.drought_hindcast.indicator_data import (
    INDICATOR_COMBINATIONS_FILE,
    IOD_SKILL_FILE,
)
from analysis.drought_hindcast.indicator_definitions import (
    get_iod_region_seasons,
    IOD_DROUGHT_PHASES,
    IodPhase,
    MAIN_IOD_ALERT_RULE,
    MAIN_IOD_INDEX_MONTH_COUNT,
    MAIN_IOD_SOURCE,
)
from analysis.drought_hindcast.plot_skill import (
    DEFAULT_DROUGHT_DEFINITION,
    draw_measures,
    DROUGHT_DEFINITION_LABELS,
    finish_figure,
    GRID_COLOUR,
    LEAD_TIME_AXIS_LABEL,
    LEAD_TIME_MEASURE_OFFSET,
    MEASURE_LABELS,
    NEUTRAL_COLOUR,
    NO_SKILL_LINE_STYLE,
    save_figure,
    style_percent_axis,
)
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.ticker import PercentFormatter

IOD_COLOUR = "#7c3aed"
EITHER_COLOUR = "#2f855a"
BOTH_COLOUR = "#b45309"
OTHER_SOURCE_OPACITY = 0.35
# One width for every ROC chart, so that their text is the same size on a slide.
ROC_AREA_FIGURE_WIDTH_INCHES = 12
ROC_AREA_LIMITS = (0.3, 1)
RUN_MONTH_AXIS_LABEL = f"{LEAD_TIME_AXIS_LABEL}, and the month of the run"
DROUGHT_LABEL = DROUGHT_DEFINITION_LABELS[DEFAULT_DROUGHT_DEFINITION].lower()
DESCRIPTION = (
    f"IOD: {MAIN_IOD_SOURCE.value}, index of the month before the run, in the outer "
    f"third of its own values; {DROUGHT_LABEL}"
)
# The region-seasons of each phase get a chart of their own.
ROC_AREA_FILE_NAMES: dict[IodPhase, str] = {
    IodPhase.NEGATIVE: "iod_roc_area_short_rains",
    IodPhase.POSITIVE: "iod_roc_area_zimbabwe",
}
# Label and line style per combination; a SEAS5 threshold shares the colour of the
# combination that alerts about as often.
COMBINATION_STYLES: dict[Combination, tuple[str, dict[str, str | float]]] = {
    Combination.SEAS5: ("SEAS5, 40% of members dry", {"color": SEAS5_COLOUR}),
    Combination.IOD: ("IOD", {"color": IOD_COLOUR}),
    Combination.EITHER: ("Either", {"color": EITHER_COLOUR}),
    Combination.SEAS5_AT_LOWER_THRESHOLD: (
        "SEAS5, 30% of members dry",
        {"color": EITHER_COLOUR, "linestyle": "--"},
    ),
    Combination.BOTH: ("Both", {"color": BOTH_COLOUR}),
    Combination.SEAS5_AT_HIGHER_THRESHOLD: (
        "SEAS5, 50% of members dry",
        {"color": BOTH_COLOUR, "linestyle": "--"},
    ),
    Combination.ALL_WITH_SKILL: (
        "All that have skill",
        {"color": NEUTRAL_COLOUR, "linestyle": ":"},
    ),
}
# The alerts that use IOD, as points next to SEAS5 alone at its three thresholds.
IOD_ALERT_COLOURS: dict[Combination, str] = {
    Combination.IOD: IOD_COLOUR,
    Combination.EITHER: EITHER_COLOUR,
    Combination.BOTH: BOTH_COLOUR,
}
TRADE_OFF_MONTHS_BEFORE_SEASON = (1, 0)
TRADE_OFF_FALSE_ALARM_RATIO_LIMITS = (0.2, 0.75)
TRADE_OFF_MARKER_SIZE = 70
TRADE_OFF_FIGURE_WIDTH_INCHES = 9
POINT_LABEL_OFFSET = 9


def main() -> None:
    iod_skill = pd.read_csv(IOD_SKILL_FILE)
    iod_skill = iod_skill.loc[
        (iod_skill["drought_definition"] == DEFAULT_DROUGHT_DEFINITION)
        & (iod_skill["index_month_count"] == MAIN_IOD_INDEX_MONTH_COUNT)
        & (iod_skill["alert_rule"] == MAIN_IOD_ALERT_RULE.value)
    ]
    combinations = pd.read_csv(INDICATOR_COMBINATIONS_FILE)
    region_seasons = get_iod_region_seasons()
    pooled_names = [
        region_season.name
        for region_season in region_seasons
        if region_season.is_in_pooled_results
    ]

    plot_roc_areas(iod_skill, combinations, region_seasons, "iod_roc_area")
    for drought_phase, file_name in ROC_AREA_FILE_NAMES.items():
        plot_roc_areas(
            iod_skill,
            combinations,
            [
                region_season
                for region_season in region_seasons
                if IOD_DROUGHT_PHASES[region_season.name] == drought_phase
            ],
            file_name,
        )
    _plot_iod_alerts(
        iod_skill.loc[iod_skill["iod_source"] == MAIN_IOD_SOURCE.value], region_seasons
    )
    _plot_combinations(
        combinations,
        [POOLED_IOD_REGION_SEASONS, *pooled_names],
        "indicator_combinations",
    )
    _plot_trade_off(combinations, POOLED_IOD_REGION_SEASONS, "indicator_trade_off")


def plot_roc_areas(
    iod_skill: pd.DataFrame,
    combinations: pd.DataFrame,
    region_seasons: list[RegionSeason],
    file_name: str,
) -> None:
    """ROC area per lead time: SEAS5 against the IOD index of every source.

    A filled marker passes the skill review's bar for Include.
    """
    figure, axes = create_panels(
        row_count=1,
        column_count=len(region_seasons),
        shares_lead_times=False,
        figure_width_inches=ROC_AREA_FIGURE_WIDTH_INCHES,
    )
    for axis, region_season in zip(axes[0], region_seasons, strict=True):
        region_iod_skill = iod_skill.loc[iod_skill["scope"] == region_season.name]
        for source, source_skill in region_iod_skill.groupby("iod_source"):
            if source == MAIN_IOD_SOURCE.value:
                _draw_roc_areas(axis, source_skill, IOD_COLOUR)
            else:
                axis.plot(
                    source_skill["months_until_season_start"],
                    source_skill["roc_area"],
                    color=IOD_COLOUR,
                    linewidth=1,
                    alpha=OTHER_SOURCE_OPACITY,
                )
        _draw_roc_areas(
            axis,
            combinations.loc[
                (combinations["scope"] == region_season.name)
                & (combinations["combination"] == Combination.SEAS5.value)
            ],
            SEAS5_COLOUR,
        )
        for level in (READINESS_MINIMUM_ROC_AREA, INCLUDE_MINIMUM_ROC_AREA):
            axis.axhline(
                level, color=NEUTRAL_COLOUR, linestyle=NO_SKILL_LINE_STYLE, linewidth=1
            )
        axis.set_ylim(*ROC_AREA_LIMITS)
        axis.grid(axis="y", color=GRID_COLOUR)
        axis.set_axisbelow(True)
        axis.spines[["top", "right"]].set_visible(False)
        axis.tick_params(length=0)
        axis.set_title(
            region_season.name, loc="left", fontsize="medium", fontweight="bold"
        )
        set_lead_time_axis(axis, first_season_month=region_season.months[0])
    figure.supylabel("ROC area", fontsize="medium")
    add_legend(
        figure,
        [
            Line2D([], [], color=SEAS5_COLOUR, linewidth=2, marker="o", label="SEAS5"),
            Line2D(
                [],
                [],
                color=IOD_COLOUR,
                linewidth=2,
                marker="o",
                label=f"IOD, {MAIN_IOD_SOURCE.value}",
            ),
            Line2D(
                [],
                [],
                color=IOD_COLOUR,
                alpha=OTHER_SOURCE_OPACITY,
                label="IOD, other sources",
            ),
            Line2D(
                [],
                [],
                color=NEUTRAL_COLOUR,
                linestyle="",
                marker="o",
                markerfacecolor="white",
                markeredgewidth=1.5,
                label="Short of the skill review's bar",
            ),
            Line2D(
                [],
                [],
                color=NEUTRAL_COLOUR,
                linestyle=NO_SKILL_LINE_STYLE,
                label=(
                    f"No skill ({READINESS_MINIMUM_ROC_AREA}) and the bar "
                    f"({INCLUDE_MINIMUM_ROC_AREA}, and unlikely by chance)"
                ),
            ),
        ],
        "ROC area: the chance that a drought year scores higher than another year; "
        f"{DROUGHT_LABEL}",
        x_label=RUN_MONTH_AXIS_LABEL,
    )
    save_figure(figure, file_name)


def _draw_roc_areas(axis: Axes, scores: pd.DataFrame, colour: str) -> None:
    months = scores["months_until_season_start"]
    passes_bar = pd.Series(
        [
            get_measured_level(roc_area, probability_by_chance) == SkillLevel.INCLUDE
            for roc_area, probability_by_chance in zip(
                scores["roc_area"],
                scores["roc_area_probability_by_chance"],
                strict=True,
            )
        ],
        index=scores.index,
    )
    axis.plot(months, scores["roc_area"], color=colour, linewidth=2)
    axis.scatter(
        months[passes_bar], scores["roc_area"][passes_bar], color=colour, zorder=3
    )
    axis.scatter(
        months[~passes_bar],
        scores["roc_area"][~passes_bar],
        facecolor="white",
        edgecolor=colour,
        linewidth=1.5,
        zorder=3,
    )


def _plot_iod_alerts(
    iod_skill: pd.DataFrame, region_seasons: list[RegionSeason]
) -> None:
    """Hit rate and false-alarm ratio of the IOD alert, per region-season."""
    figure, axes = create_panels(row_count=1, column_count=len(region_seasons))
    for axis, region_season in zip(axes[0], region_seasons, strict=True):
        scores = iod_skill.loc[iod_skill["scope"] == region_season.name].sort_values(
            "months_until_season_start", ascending=False
        )
        draw_measures(
            axis, scores["months_until_season_start"], scores, LEAD_TIME_MEASURE_OFFSET
        )
        style_percent_axis(axis, region_season.name)
        set_lead_time_axis(axis)
    finish_figure(
        figure, DESCRIPTION, "iod_skill_by_region_season", shows_partial_seasons=False
    )


def _plot_combinations(
    combinations: pd.DataFrame, scopes: list[str], file_name: str
) -> None:
    """Both measures per lead time, one line per combination of SEAS5 and IOD."""
    figure, axes = create_panels(
        row_count=len(MEASURE_LABELS), column_count=len(scopes)
    )
    for measure_axes, (measure, measure_label) in zip(
        axes, MEASURE_LABELS.items(), strict=True
    ):
        for axis, scope in zip(measure_axes, scopes, strict=True):
            scope_scores = combinations.loc[combinations["scope"] == scope]
            for combination, (_, line_style) in COMBINATION_STYLES.items():
                scores = scope_scores.loc[
                    scope_scores["combination"] == combination.value
                ]
                axis.plot(
                    scores["months_until_season_start"],
                    scores[measure],
                    linewidth=1.8,
                    **line_style,
                )
            style_percent_axis(axis, scope)
            set_lead_time_axis(axis)
        measure_axes[0].set_ylabel(measure_label)
    add_legend(
        figure,
        [
            Line2D([], [], linewidth=1.8, label=label, **line_style)
            for label, line_style in COMBINATION_STYLES.values()
        ],
        DESCRIPTION,
    )
    save_figure(figure, file_name)


def _plot_trade_off(combinations: pd.DataFrame, scope: str, file_name: str) -> None:
    """Hit rate against false-alarm ratio: SEAS5 alone at three thresholds, and the
    alerts that use IOD. An alert is better the further up and to the left it is.
    """
    figure, axes = create_panels(
        row_count=1,
        column_count=len(TRADE_OFF_MONTHS_BEFORE_SEASON),
        shares_lead_times=False,
        figure_width_inches=TRADE_OFF_FIGURE_WIDTH_INCHES,
    )
    for axis, months_before_season in zip(
        axes[0], TRADE_OFF_MONTHS_BEFORE_SEASON, strict=True
    ):
        scores = combinations.loc[
            (combinations["scope"] == scope)
            & (combinations["months_until_season_start"] == months_before_season)
        ].set_index("combination")
        seas5_scores = scores.loc[
            [
                combination.value
                for combination in sorted(SEAS5_THRESHOLDS, key=SEAS5_THRESHOLDS.get)
            ]
        ]
        axis.plot(
            seas5_scores["false_alarm_ratio"],
            seas5_scores["hit_rate"],
            color=SEAS5_COLOUR,
            linewidth=2,
            marker="o",
        )
        for combination, threshold in SEAS5_THRESHOLDS.items():
            _label_point(
                axis,
                scores.loc[combination.value],
                f"SEAS5 at {threshold:.0%}",
                SEAS5_COLOUR,
                is_left_of_point=True,
            )
        for combination, colour in IOD_ALERT_COLOURS.items():
            label, _ = COMBINATION_STYLES[combination]
            point = scores.loc[combination.value]
            axis.scatter(
                point["false_alarm_ratio"],
                point["hit_rate"],
                color=colour,
                s=TRADE_OFF_MARKER_SIZE,
                zorder=3,
            )
            _label_point(axis, point, label, colour, is_left_of_point=False)
        axis.axvline(
            1 - scores["drought_frequency"].iloc[0],
            color=NEUTRAL_COLOUR,
            linestyle=NO_SKILL_LINE_STYLE,
            linewidth=1,
        )
        style_percent_axis(axis, _format_lead_time(months_before_season))
        axis.set_xlim(*TRADE_OFF_FALSE_ALARM_RATIO_LIMITS)
        axis.xaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
        axis.grid(axis="x", color=GRID_COLOUR)
    axes[0][0].set_ylabel("Hit rate (higher is better)")
    add_legend(
        figure,
        [
            Line2D(
                [],
                [],
                color=SEAS5_COLOUR,
                linewidth=2,
                marker="o",
                label="SEAS5 alone, by share of members that must be dry",
            ),
            Line2D(
                [],
                [],
                color=NEUTRAL_COLOUR,
                linestyle=NO_SKILL_LINE_STYLE,
                label="False-alarm ratio without skill",
            ),
        ],
        f"{scope}; {DROUGHT_LABEL}",
        x_label="False-alarm ratio (lower is better)",
    )
    save_figure(figure, file_name)


def _label_point(
    axis: Axes, point: pd.Series, label: str, colour: str, is_left_of_point: bool
) -> None:
    axis.annotate(
        label,
        (point["false_alarm_ratio"], point["hit_rate"]),
        xytext=(-POINT_LABEL_OFFSET if is_left_of_point else POINT_LABEL_OFFSET, 0),
        textcoords="offset points",
        ha="right" if is_left_of_point else "left",
        va="center",
        color=colour,
        fontsize="small",
        fontweight="bold",
    )


def _format_lead_time(months_before_season: int) -> str:
    if months_before_season == 0:
        return "At the season start"
    month_word = "month" if months_before_season == 1 else "months"
    return f"{months_before_season} {month_word} before the season"


if __name__ == "__main__":
    main()
