"""Chart parts shared by the charts of the indicators that are set next to SEAS5."""

from collections.abc import Callable

import pandas as pd
from analysis.drought_hindcast.compare_with_skill_review import (
    DARK_TEXT_COLOUR,
    LEVEL_COLOURS,
    LEVEL_TEXT_COLOURS,
    MONTH_ABBREVIATIONS,
    NO_ALERTS_TEXT,
    RULE_MARKER_OFFSET,
    RULE_MARKER_SIZE,
    SkillLevel,
)
from analysis.drought_hindcast.plot_skill import GRID_COLOUR, LEAD_TIME_AXIS_LABEL
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

SEAS5_COLOUR = "#111827"
PANEL_SIZE_INCHES = (3.4, 2.9)
# Leaves room for the legend above a figure with few panels.
MINIMUM_FIGURE_WIDTH_INCHES = 12
LEGEND_HEIGHT_INCHES = 0.9
LEGEND_COLUMN_COUNT = 4
MONTHS_PER_YEAR = 12
GRID_CELL_FONT_SIZE = "x-small"


def create_panels(
    row_count: int,
    column_count: int,
    shares_lead_times: bool = True,
    figure_width_inches: float | None = None,
    panel_height_inches: float = PANEL_SIZE_INCHES[1],
) -> tuple[Figure, list[list[Axes]]]:
    """A row or grid of panels under a legend. A smaller figure gives larger text on a slide."""
    panel_width, _ = PANEL_SIZE_INCHES
    figure = Figure(
        figsize=(
            figure_width_inches
            or max(column_count * panel_width, MINIMUM_FIGURE_WIDTH_INCHES),
            row_count * panel_height_inches + LEGEND_HEIGHT_INCHES,
        ),
        layout="constrained",
    )
    axes = figure.subplots(
        row_count, column_count, sharex=shares_lead_times, sharey=True, squeeze=False
    )
    return figure, [list(row) for row in axes]


def set_lead_time_axis(axis: Axes, first_season_month: int | None = None) -> None:
    """Lead times from early to late; with the first season month, also the run months."""
    earliest, latest = sorted(axis.get_xlim(), reverse=True)
    months_before_season = range(round(latest + 0.2), round(earliest - 0.2) + 1)
    axis.set_xticks(months_before_season)
    if first_season_month is not None:
        axis.set_xticklabels(
            [
                f"{months}\n"
                + MONTH_ABBREVIATIONS[
                    (first_season_month - months - 1) % MONTHS_PER_YEAR
                ]
                for months in months_before_season
            ]
        )
    axis.set_xlim(earliest, latest)


def add_legend(
    figure: Figure,
    entries: list[Line2D],
    title: str,
    x_label: str = LEAD_TIME_AXIS_LABEL,
) -> None:
    figure.supxlabel(x_label, fontsize="medium")
    figure.legend(
        handles=entries,
        title=title,
        alignment="left",
        loc="outside upper left",
        ncols=min(len(entries), LEGEND_COLUMN_COUNT),
        frameon=False,
        fontsize="small",
    )


def draw_level_grid(
    axis: Axes,
    cells: pd.DataFrame,
    row_names: list[str],
    column_name: str,
    column_values: list[int],
    get_text: Callable[[pd.Series], str],
    level_column: str,
    title: str,
    has_marker_column: str | None = None,
    format_column: Callable[[int], str] = str,
) -> None:
    """A grid of region-season by `column_name`. Each cell is coloured by its level, and
    carries a dot where `has_marker_column` is Include.
    """
    for _, cell in cells.iterrows():
        level = SkillLevel(cell[level_column])
        column = column_values.index(cell[column_name])
        row = row_names.index(cell["region_season"])
        axis.add_patch(
            Rectangle(
                (column - 0.5, row - 0.5),
                1,
                1,
                facecolor=LEVEL_COLOURS[level],
                edgecolor="white",
                linewidth=2,
            )
        )
        axis.text(
            column,
            row,
            get_text(cell),
            horizontalalignment="center",
            verticalalignment="center",
            fontsize=GRID_CELL_FONT_SIZE,
            color=LEVEL_TEXT_COLOURS[level],
        )
        if (
            has_marker_column is not None
            and cell[has_marker_column] == SkillLevel.INCLUDE.value
        ):
            marker_column_offset, marker_row_offset = RULE_MARKER_OFFSET
            axis.scatter(
                column + marker_column_offset,
                row + marker_row_offset,
                s=RULE_MARKER_SIZE,
                color=DARK_TEXT_COLOUR,
                edgecolor="white",
                linewidth=0.8,
                zorder=3,
            )
    axis.set_xlim(-0.5, len(column_values) - 0.5)
    axis.set_ylim(len(row_names) - 0.5, -0.5)
    axis.set_xticks(
        range(len(column_values)), [format_column(value) for value in column_values]
    )
    axis.set_yticks(range(len(row_names)), row_names)
    axis.tick_params(length=0)
    axis.spines[:].set_color(GRID_COLOUR)
    axis.set_title(title, loc="left", fontsize="medium", fontweight="bold")


def format_scores(cell: pd.Series) -> str:
    """Hit rate and false-alarm ratio in percent; the ratio is undefined without alerts."""
    false_alarm_ratio = (
        NO_ALERTS_TEXT
        if pd.isna(cell["false_alarm_ratio"])
        else f"{cell['false_alarm_ratio'] * 100:.0f}"
    )
    return f"{cell['hit_rate'] * 100:.0f}/{false_alarm_ratio}"


def create_level_patches(legend_labels: dict[SkillLevel, str]) -> list[Patch]:
    return [
        Patch(facecolor=LEVEL_COLOURS[level], label=label)
        for level, label in legend_labels.items()
    ]
