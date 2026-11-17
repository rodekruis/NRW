"""Chart parts shared by the charts of the indicators that are set next to SEAS5."""

from analysis.drought_hindcast.compare_with_skill_review import MONTH_ABBREVIATIONS
from analysis.drought_hindcast.plot_skill import LEAD_TIME_AXIS_LABEL
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

SEAS5_COLOUR = "#111827"
PANEL_SIZE_INCHES = (3.4, 2.9)
# Leaves room for the legend above a figure with few panels.
MINIMUM_FIGURE_WIDTH_INCHES = 12
LEGEND_HEIGHT_INCHES = 0.9
LEGEND_COLUMN_COUNT = 4
MONTHS_PER_YEAR = 12


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
