"""Draw the skill charts: hit rate and false-alarm ratio by lead time, in several breakdowns."""

import pandas as pd
from analysis.drought_hindcast.calculate_skill import (
    ALL_REGION_SEASONS,
    UNCERTAINTY_PERCENTILES,
)
from analysis.drought_hindcast.definitions import (
    DEFAULT_PROBABILITY_THRESHOLD,
    POOLED_REGION_SEASONS,
    PROBABILITY_THRESHOLDS,
    RegionSeason,
)
from analysis.drought_hindcast.study_area import (
    CHARTS_DIRECTORY,
    FIRST_YEAR,
    SKILL_FILE,
)
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.offsetbox import AnchoredOffsetbox, HPacker, TextArea, VPacker
from matplotlib.ticker import PercentFormatter
from scipy.stats import beta

HIT_RATE_COLOUR = "#1b6ca8"
FALSE_ALARM_RATIO_COLOUR = "#d8642a"
NEUTRAL_COLOUR = "#6b7280"
GRID_COLOUR = "#e5e7eb"
RANGE_OPACITY = 0.45
# Sideways shift, in months, that keeps the ranges of the two measures apart.
LEAD_TIME_MEASURE_OFFSET = 0.05
MEASURE_OFFSET_DIRECTIONS = {"hit_rate": -1, "false_alarm_ratio": 1}
LEAD_TIME_AXIS_LABEL = "Months before the season starts"
LEGEND_COLUMN_WIDTH_INCHES = 2.6
RESOLUTION_DOTS_PER_INCH = 150
PERCENT_TICKS = (0, 0.25, 0.5, 0.75, 1)
NO_SKILL_LINE_STYLE = (0, (2, 2))

MEASURE_LABELS = {"hit_rate": "Hit rate", "false_alarm_ratio": "False-alarm ratio"}
MEASURE_COLOURS = {
    "hit_rate": HIT_RATE_COLOUR,
    "false_alarm_ratio": FALSE_ALARM_RATIO_COLOUR,
}
# The region rule at each threshold. The area rule is scored too, but not drawn here.
RULE_LABELS = {
    f"probability_{threshold}": f"At least {threshold:.0%} of members dry"
    for threshold in PROBABILITY_THRESHOLDS
}
DROUGHT_DEFINITION_LABELS = {
    "driest_third": "Drought = driest third of years",
    "driest_fifth": "Drought = driest fifth of years",
}
DEFAULT_RULE = f"probability_{DEFAULT_PROBABILITY_THRESHOLD}"
DEFAULT_DROUGHT_DEFINITION = "driest_third"
POOLED_LABEL = f"all {len(POOLED_REGION_SEASONS)} region-seasons"
REGION_SEASON_GRID_COLUMN_COUNT = 4
REGION_SEASON_PANEL_SIZE_INCHES = (3, 2.6)
# Lead time whose values are written out in a chip at the top of a panel.
CHIP_MONTHS_BEFORE_SEASON = 1
CHIP_FONT_SIZE = "small"
CHIP_BACKGROUND_COLOUR = "#f9fafb"


def main() -> None:
    skill = pd.read_csv(SKILL_FILE)

    _plot_all_region_seasons(skill)
    _plot_by_alert_rule(skill)
    _plot_by_drought_definition(skill)
    for rule_name in RULE_LABELS:
        plot_region_seasons(
            skill,
            POOLED_REGION_SEASONS,
            rule_name,
            REGION_SEASON_GRID_COLUMN_COUNT,
            f"skill_by_region_season_{rule_name}",
        )


def _plot_all_region_seasons(skill: pd.DataFrame) -> None:
    figure = Figure(figsize=(7.5, 6), layout="constrained")
    axis = figure.subplots()
    draw_skill_panel(
        axis,
        select_scores(
            skill, ALL_REGION_SEASONS, DEFAULT_RULE, DEFAULT_DROUGHT_DEFINITION
        ),
        capitalise(POOLED_LABEL),
    )
    finish_figure(
        figure,
        f"{RULE_LABELS[DEFAULT_RULE]}; "
        f"{DROUGHT_DEFINITION_LABELS[DEFAULT_DROUGHT_DEFINITION].lower()}",
        "skill_all_region_seasons",
    )


def _plot_by_alert_rule(skill: pd.DataFrame) -> None:
    figure = Figure(figsize=(13.5, 5.2), layout="constrained")
    axes = figure.subplots(1, len(RULE_LABELS), sharey=True)
    for axis, (rule_name, rule_label) in zip(axes, RULE_LABELS.items(), strict=True):
        draw_skill_panel(
            axis,
            select_scores(
                skill, ALL_REGION_SEASONS, rule_name, DEFAULT_DROUGHT_DEFINITION
            ),
            rule_label,
            chip_months_before_season=CHIP_MONTHS_BEFORE_SEASON,
        )
    finish_figure(
        figure,
        f"{capitalise(POOLED_LABEL)}; "
        f"{DROUGHT_DEFINITION_LABELS[DEFAULT_DROUGHT_DEFINITION].lower()}",
        "skill_by_alert_rule",
    )


def _plot_by_drought_definition(skill: pd.DataFrame) -> None:
    figure = Figure(figsize=(9.5, 5.5), layout="constrained")
    axes = figure.subplots(1, len(DROUGHT_DEFINITION_LABELS), sharey=True)
    for axis, (definition_name, definition_label) in zip(
        axes, DROUGHT_DEFINITION_LABELS.items(), strict=True
    ):
        draw_skill_panel(
            axis,
            select_scores(skill, ALL_REGION_SEASONS, DEFAULT_RULE, definition_name),
            definition_label,
        )
    finish_figure(
        figure,
        f"{capitalise(POOLED_LABEL)}; " f"{RULE_LABELS[DEFAULT_RULE].lower()}",
        "skill_by_drought_definition",
    )


def plot_region_seasons(
    skill: pd.DataFrame,
    region_seasons: list[RegionSeason],
    rule_name: str,
    column_count: int,
    file_name: str,
) -> None:
    row_count = -(-len(region_seasons) // column_count)
    panel_width, panel_height = REGION_SEASON_PANEL_SIZE_INCHES
    figure = Figure(
        figsize=(column_count * panel_width, row_count * panel_height + 0.6),
        layout="constrained",
    )
    axes = figure.subplots(
        row_count, column_count, sharex=True, sharey=True, squeeze=False
    )
    for axis, region_season in zip(
        axes.flat[: len(region_seasons)], region_seasons, strict=True
    ):
        draw_skill_panel(
            axis,
            select_scores(
                skill, region_season.name, rule_name, DEFAULT_DROUGHT_DEFINITION
            ),
            region_season.name,
        )
    for position in range(len(region_seasons), axes.size):
        axes.flat[position].set_visible(False)
        # The panel above is now the lowest of its column, so it carries the labels.
        axes.flat[position - column_count].tick_params(labelbottom=True)
    finish_figure(
        figure,
        f"{RULE_LABELS[rule_name]}; "
        f"{DROUGHT_DEFINITION_LABELS[DEFAULT_DROUGHT_DEFINITION].lower()}",
        file_name,
    )


def capitalise(label: str) -> str:
    return label[0].upper() + label[1:]


def select_scores(
    skill: pd.DataFrame, scope: str, rule_name: str, definition_name: str
) -> pd.DataFrame:
    return skill.loc[
        (skill["scope"] == scope)
        & (skill["alert_rule"] == rule_name)
        & (skill["drought_definition"] == definition_name)
    ].sort_values("months_until_season_start", ascending=False)


def draw_skill_panel(
    axis: Axes,
    scores: pd.DataFrame,
    title: str,
    chip_months_before_season: int | None = None,
) -> None:
    """The recurring chart: both measures against the months left until the season starts."""
    months = scores["months_until_season_start"]
    draw_measures(
        axis,
        months,
        scores,
        LEAD_TIME_MEASURE_OFFSET,
        is_filled=scores["full_season_share"] == 1,
    )
    axis.set_xticks(months)
    axis.set_xlim(months.max() + 0.3, months.min() - 0.3)
    style_percent_axis(axis, title)
    if chip_months_before_season is not None:
        _draw_value_chip(axis, scores, chip_months_before_season)


def draw_measures(
    axis: Axes,
    x_values: pd.Series,
    scores: pd.DataFrame,
    measure_offset: float,
    is_filled: pd.Series | None = None,
) -> None:
    """Both measures with their ranges and no-skill levels; open markers where not filled."""
    if is_filled is None:
        is_filled = pd.Series(True, index=scores.index)
    no_skill_levels = {
        # Alerts unrelated to droughts catch as many droughts as they are frequent.
        "hit_rate": scores["alert_frequency"],
        "false_alarm_ratio": 1 - scores["drought_frequency"],
    }
    for measure, colour in MEASURE_COLOURS.items():
        positions = x_values + MEASURE_OFFSET_DIRECTIONS[measure] * measure_offset
        axis.vlines(
            positions,
            scores[f"{measure}_low"],
            scores[f"{measure}_high"],
            color=colour,
            alpha=RANGE_OPACITY,
            linewidth=1.5,
        )
        axis.plot(
            x_values,
            no_skill_levels[measure],
            color=colour,
            linestyle=NO_SKILL_LINE_STYLE,
            linewidth=1,
        )
        axis.plot(positions, scores[measure], color=colour, linewidth=2)
        axis.scatter(
            positions[is_filled],
            scores[measure][is_filled],
            color=colour,
            zorder=3,
        )
        axis.scatter(
            positions[~is_filled],
            scores[measure][~is_filled],
            facecolor="white",
            edgecolor=colour,
            linewidth=1.5,
            zorder=3,
        )


def _draw_value_chip(
    axis: Axes, scores: pd.DataFrame, months_before_season: int
) -> None:
    """Write out both measures for one lead time, in the empty top of the panel."""
    values = scores.loc[
        scores["months_until_season_start"] == months_before_season
    ].iloc[0]
    # From the counts: the stored shares are rounded, and rounding twice can be a point off.
    shares = {
        "hit_rate": values["hit_count"] / values["drought_count"],
        "false_alarm_ratio": 1 - values["hit_count"] / values["alert_count"],
    }
    month_word = "month" if months_before_season == 1 else "months"
    heading = TextArea(
        f"{months_before_season} {month_word} before the season",
        textprops={"color": NEUTRAL_COLOUR, "fontsize": CHIP_FONT_SIZE},
    )
    measures = HPacker(
        children=[
            TextArea(
                f"{label} {shares[measure]:.0%}",
                textprops={
                    "color": MEASURE_COLOURS[measure],
                    "fontsize": CHIP_FONT_SIZE,
                    "fontweight": "bold",
                },
            )
            for measure, label in MEASURE_LABELS.items()
        ],
        sep=8,
    )
    chip = AnchoredOffsetbox(
        loc="upper center",
        child=VPacker(children=[heading, measures], align="center", sep=3),
        pad=0.5,
        borderpad=0.6,
    )
    chip.patch.set_boxstyle("round,pad=0.2")
    chip.patch.set_facecolor(CHIP_BACKGROUND_COLOUR)
    chip.patch.set_edgecolor(GRID_COLOUR)
    axis.add_artist(chip)


def get_binomial_range(count: int, total: int) -> tuple[float, float]:
    """Exact (Clopper-Pearson) range for a share of independent cases."""
    low_percentile, high_percentile = (
        percentile / 100 for percentile in UNCERTAINTY_PERCENTILES
    )
    low = beta.ppf(low_percentile, count, total - count + 1) if count > 0 else 0
    high = beta.ppf(high_percentile, count + 1, total - count) if count < total else 1
    return float(low), float(high)


def style_percent_axis(axis: Axes, title: str) -> None:
    axis.set_ylim(0, 1)
    axis.set_yticks(PERCENT_TICKS)
    axis.yaxis.set_major_formatter(PercentFormatter(xmax=1))
    axis.grid(axis="y", color=GRID_COLOUR)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)
    axis.tick_params(length=0)
    axis.set_title(title, loc="left", fontsize="medium", fontweight="bold")


def finish_figure(
    figure: Figure,
    description: str,
    file_name: str,
    x_label: str = LEAD_TIME_AXIS_LABEL,
    shows_partial_seasons: bool = True,
) -> None:
    low_percentile, high_percentile = UNCERTAINTY_PERCENTILES
    legend_entries = [
        *[
            Line2D(
                [],
                [],
                color=MEASURE_COLOURS[measure],
                linewidth=2,
                marker="o",
                label=label,
            )
            for measure, label in MEASURE_LABELS.items()
        ],
        Line2D(
            [],
            [],
            color=NEUTRAL_COLOUR,
            alpha=RANGE_OPACITY,
            linestyle="",
            marker="|",
            markersize=14,
            markeredgewidth=1.5,
            label=f"{high_percentile - low_percentile:.0f}% range",
        ),
        Line2D(
            [],
            [],
            color=NEUTRAL_COLOUR,
            linestyle=NO_SKILL_LINE_STYLE,
            linewidth=1,
            label="Level without skill",
        ),
    ]
    if shows_partial_seasons:
        legend_entries.append(
            Line2D(
                [],
                [],
                color=NEUTRAL_COLOUR,
                linestyle="",
                marker="o",
                markerfacecolor="white",
                markeredgewidth=1.5,
                label="Part of season forecast",
            )
        )
    figure.supxlabel(x_label, fontsize="medium")
    figure.legend(
        handles=legend_entries,
        title=f"{description}; seasons from {FIRST_YEAR}",
        alignment="left",
        loc="outside upper left",
        ncols=min(
            len(legend_entries),
            int(figure.get_figwidth() / LEGEND_COLUMN_WIDTH_INCHES),
        ),
        frameon=False,
        fontsize="small",
    )
    save_figure(figure, file_name)


def save_figure(figure: Figure, file_name: str) -> None:
    CHARTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    path = CHARTS_DIRECTORY / f"{file_name}.png"
    figure.savefig(path, dpi=RESOLUTION_DOTS_PER_INCH)
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
