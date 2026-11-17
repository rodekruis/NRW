"""Set the FEWS NET grades of the skill review next to what is measured here, per
region-season and issue month.

The review grades an issue month Include when the near-term projection of that month
reaches the impact window of the season: its last two months and the three months after.
Here the projection that covers most of that window is scored on whether it tells the
seasons with a rainfall drought apart.
"""

from collections.abc import Callable

import numpy as np
import pandas as pd
from analysis.drought_hindcast.calculate_fews_net_alerts import (
    calculate_own_terciles,
    calculate_rank_among_others,
    load_region_phases,
    REPORT_MONTH_COLUMN,
    select_projection,
)
from analysis.drought_hindcast.calculate_skill import BOOTSTRAP_SEED, to_booleans
from analysis.drought_hindcast.compare_with_skill_review import (
    DARK_TEXT_COLOUR,
    get_measured_level,
    get_rule_level,
    INCLUDE_MINIMUM_ROC_AREA,
    LEGEND_PLACEMENT,
    LEVEL_COLOURS,
    LEVEL_TEXT_COLOURS,
    MONTH_ABBREVIATIONS,
    NO_ALERTS_TEXT,
    REVIEW_LEGEND_LABELS,
    RULE_LEGEND_LABELS,
    RULE_MARKER_OFFSET,
    RULE_MARKER_SIZE,
    SkillLevel,
)
from analysis.drought_hindcast.definitions import (
    get_observed_drought_column,
    POOLED_REGION_SEASONS,
    RegionSeason,
)
from analysis.drought_hindcast.indicator_data import (
    SKILL_REVIEW_FEWS_NET_COMPARISON_FILE,
    SKILL_REVIEW_FEWS_NET_GRADES_FILE,
    SKILL_REVIEW_FEWS_NET_POOLED_FILE,
)
from analysis.drought_hindcast.indicator_definitions import (
    FEWS_NET_MAXIMUM_CURRENT_SITUATION_AGE_MONTHS,
    FEWS_NET_MINIMUM_SEASON_COUNT,
)
from analysis.drought_hindcast.indicator_scoring import (
    measure_discrimination,
    score_alert,
)
from analysis.drought_hindcast.plot_skill import (
    DEFAULT_DROUGHT_DEFINITION,
    GRID_COLOUR,
    NEUTRAL_COLOUR,
    save_figure,
)
from analysis.drought_hindcast.prepare_fews_net import CRISIS_OR_WORSE_COLUMN
from analysis.drought_hindcast.prepare_iod import MONTH_FREQUENCY
from analysis.drought_hindcast.study_area import OBSERVED_SEASONS_FILE
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

CURRENT_SITUATION_SCENARIO = "CS"
# Issue months, counted from the last month of the season; negative is before it.
ISSUE_MONTHS_AFTER_SEASON_END = range(-5, 5)
# The impact window of the review: the last two season months and the three months after.
IMPACT_WINDOW_MONTHS_BEFORE_SEASON_END = 1
IMPACT_WINDOW_MONTH_COUNT = 5
OFFSET_COLUMN = "months_after_season_end"
CELL_FONT_SIZE = "x-small"


def main() -> None:
    phases = load_region_phases()
    observed = pd.read_csv(OBSERVED_SEASONS_FILE)
    cases = pd.concat(
        build_issue_month_cases(
            phases.loc[phases["region_key"] == region_season.region_key],
            observed.loc[observed["region_season"] == region_season.name],
            region_season,
        )
        for region_season in POOLED_REGION_SEASONS
    )
    random_generator = np.random.default_rng(BOOTSTRAP_SEED)
    measured = score_issue_months(
        cases, ["region_season", OFFSET_COLUMN, "issue_month"], random_generator
    )
    comparison = pd.read_csv(SKILL_REVIEW_FEWS_NET_GRADES_FILE).merge(
        measured, on=["region_season", "issue_month"], validate="one_to_one"
    )
    comparison["rule_level"] = [
        get_rule_level(hit_rate, alert_frequency, probability_by_chance).value
        for hit_rate, alert_frequency, probability_by_chance in zip(
            comparison["hit_rate"],
            comparison["alert_frequency"],
            comparison["probability_by_chance"],
            strict=True,
        )
    ]
    comparison["roc_level"] = [
        get_measured_level(roc_area, probability_by_chance).value
        for roc_area, probability_by_chance in zip(
            comparison["roc_area"],
            comparison["roc_area_probability_by_chance"],
            strict=True,
        )
    ]
    comparison.to_csv(SKILL_REVIEW_FEWS_NET_COMPARISON_FILE, index=False)
    print(f"Wrote {len(comparison)} rows to {SKILL_REVIEW_FEWS_NET_COMPARISON_FILE}")
    _print_agreement(comparison)
    pooled = score_issue_months(cases, [OFFSET_COLUMN], random_generator)
    pooled.to_csv(SKILL_REVIEW_FEWS_NET_POOLED_FILE, index=False)
    print(f"Wrote {len(pooled)} rows to {SKILL_REVIEW_FEWS_NET_POOLED_FILE}")
    _plot_comparison(comparison)


def build_issue_month_cases(
    region_phases: pd.DataFrame,
    observed_seasons: pd.DataFrame,
    region_season: RegionSeason,
) -> pd.DataFrame:
    """Per observed season and issue month around its end: the share in Phase 3 or worse
    in the projection that covers most of the impact window, in the latest report up to
    that month; its rank among the other seasons; and whether it gives an alert.

    Empty for a region-season with too few seasons.
    """
    projections = region_phases.loc[
        region_phases["scenario"] != CURRENT_SITUATION_SCENARIO
    ]
    report_months = projections[REPORT_MONTH_COLUMN]
    month_tables = []
    for months_after_season_end in ISSUE_MONTHS_AFTER_SEASON_END:
        rows = []
        for _, season in observed_seasons.iterrows():
            season_end = (
                pd.Period(
                    year=int(season["season_year"]),
                    month=region_season.months[0],
                    freq=MONTH_FREQUENCY,
                )
                + len(region_season.months)
                - 1
            )
            issue_month = season_end + months_after_season_end
            is_usable = (report_months <= issue_month) & (
                report_months
                >= issue_month - FEWS_NET_MAXIMUM_CURRENT_SITUATION_AGE_MONTHS
            )
            if not is_usable.any():
                continue
            projection = select_projection(
                projections.loc[report_months == report_months[is_usable].max()],
                season_end - IMPACT_WINDOW_MONTHS_BEFORE_SEASON_END,
                IMPACT_WINDOW_MONTH_COUNT,
            )
            rows.append(
                {
                    "region_season": region_season.name,
                    "season_year": int(season["season_year"]),
                    OFFSET_COLUMN: months_after_season_end,
                    "issue_month": issue_month.month,
                    "is_drought": season[
                        get_observed_drought_column(DEFAULT_DROUGHT_DEFINITION)
                    ],
                    "share": projection[CRISIS_OR_WORSE_COLUMN],
                }
            )
        month_cases = pd.DataFrame(rows)
        if len(month_cases) < FEWS_NET_MINIMUM_SEASON_COUNT:
            continue
        shares = month_cases["share"].to_numpy()
        month_cases["is_drought"] = to_booleans(month_cases, "is_drought")
        month_cases["share_rank"] = calculate_rank_among_others(shares)
        month_cases["is_alert"] = (shares > 0) & (
            shares >= calculate_own_terciles(shares)
        )
        month_tables.append(month_cases)
    return pd.concat(month_tables) if month_tables else pd.DataFrame()


def score_issue_months(
    cases: pd.DataFrame, group_columns: list[str], random_generator: np.random.Generator
) -> pd.DataFrame:
    """The alert and the ranked share scored per group of cases. Groups without
    `region_season` pool the region-seasons.
    """
    is_one_region_season = "region_season" in group_columns
    return pd.DataFrame(
        [
            {
                **dict(zip(group_columns, group_key, strict=True)),
                **score_alert(
                    is_alert=group_cases["is_alert"].to_numpy(),
                    is_drought=group_cases["is_drought"].to_numpy(),
                    season_years=group_cases["season_year"].to_numpy(),
                    is_one_region_season=is_one_region_season,
                    random_generator=random_generator,
                ),
                **measure_discrimination(
                    group_cases["share_rank"].to_numpy(),
                    group_cases["is_drought"].to_numpy(),
                    is_one_region_season=is_one_region_season,
                ),
            }
            for group_key, group_cases in cases.groupby(group_columns, sort=False)
        ]
    )


def _print_agreement(comparison: pd.DataFrame) -> None:
    """Per grade of the review and side of the season end: how many issue months pass."""
    comparison = comparison.assign(
        side=np.where(
            comparison[OFFSET_COLUMN] <= 0, "up to the season end", "after the season"
        ),
        alerts_beat_chance=comparison["rule_level"] == SkillLevel.INCLUDE.value,
        passes_review_bar=comparison["roc_level"] == SkillLevel.INCLUDE.value,
    )
    print(
        comparison.groupby(["side", "grade"])
        .agg(
            issue_months=("region_season", "size"),
            alerts_beat_chance=("alerts_beat_chance", "sum"),
            passes_review_bar=("passes_review_bar", "sum"),
        )
        .to_string()
    )


def _plot_comparison(comparison: pd.DataFrame) -> None:
    """Two grids of region-season by issue month: the review's grade, and what we measure."""
    figure = Figure(figsize=(13.5, 6), layout="constrained")
    review_axis, measured_axis = figure.subplots(1, 2, sharey=True)
    _draw_grid(
        review_axis,
        comparison,
        get_text=lambda row: MONTH_ABBREVIATIONS[int(row["issue_month"]) - 1],
        level_column="grade",
        title="Skill review: grade of FEWS NET per issue month",
    )
    review_axis.legend(
        handles=_create_level_patches(REVIEW_LEGEND_LABELS), **LEGEND_PLACEMENT
    )
    _draw_grid(
        measured_axis,
        comparison,
        get_text=_format_scores,
        level_column="rule_level",
        title="This analysis: hit rate / false-alarm ratio (%) of the FEWS NET alert",
        has_marker_column="roc_level",
    )
    measured_axis.legend(
        handles=[
            *_create_level_patches(RULE_LEGEND_LABELS),
            Line2D(
                [],
                [],
                linestyle="",
                marker="o",
                markersize=4,
                color=DARK_TEXT_COLOUR,
                label=(
                    "The projection passes the review's bar for a forecast: ROC area "
                    f"at least {INCLUDE_MINIMUM_ROC_AREA}, unlikely by chance"
                ),
            ),
        ],
        **LEGEND_PLACEMENT,
    )
    figure.supxlabel(
        "Issue month, counted from the last month of the season (0); "
        "the dashed line is the end of the season",
        fontsize="medium",
    )
    save_figure(figure, "skill_review_fews_net_comparison")


def _format_scores(row: pd.Series) -> str:
    """Hit rate and false-alarm ratio in percent; the ratio is undefined without alerts."""
    false_alarm_ratio = (
        NO_ALERTS_TEXT
        if pd.isna(row["false_alarm_ratio"])
        else f"{row['false_alarm_ratio'] * 100:.0f}"
    )
    return f"{row['hit_rate'] * 100:.0f}/{false_alarm_ratio}"


def _create_level_patches(legend_labels: dict[SkillLevel, str]) -> list[Patch]:
    return [
        Patch(facecolor=LEVEL_COLOURS[level], label=label)
        for level, label in legend_labels.items()
    ]


def _draw_grid(
    axis: Axes,
    comparison: pd.DataFrame,
    get_text: Callable[[pd.Series], str],
    level_column: str,
    title: str,
    has_marker_column: str | None = None,
) -> None:
    region_season_names = list(dict.fromkeys(comparison["region_season"]))
    offsets = list(ISSUE_MONTHS_AFTER_SEASON_END)
    for _, row in comparison.iterrows():
        level = SkillLevel(row[level_column])
        column = offsets.index(row[OFFSET_COLUMN])
        row_position = region_season_names.index(row["region_season"])
        axis.add_patch(
            Rectangle(
                (column - 0.5, row_position - 0.5),
                1,
                1,
                facecolor=LEVEL_COLOURS[level],
                edgecolor="white",
                linewidth=2,
            )
        )
        axis.text(
            column,
            row_position,
            get_text(row),
            horizontalalignment="center",
            verticalalignment="center",
            fontsize=CELL_FONT_SIZE,
            color=LEVEL_TEXT_COLOURS[level],
        )
        if (
            has_marker_column is not None
            and row[has_marker_column] == SkillLevel.INCLUDE.value
        ):
            marker_column_offset, marker_row_offset = RULE_MARKER_OFFSET
            axis.scatter(
                column + marker_column_offset,
                row_position + marker_row_offset,
                s=RULE_MARKER_SIZE,
                color=DARK_TEXT_COLOUR,
                edgecolor="white",
                linewidth=0.8,
                zorder=3,
            )
    axis.axvline(
        offsets.index(0) + 0.5, color=NEUTRAL_COLOUR, linestyle="--", linewidth=1.5
    )
    axis.set_xlim(-0.5, len(offsets) - 0.5)
    axis.set_ylim(len(region_season_names) - 0.5, -0.5)
    axis.set_xticks(range(len(offsets)), [f"{offset:+d}" for offset in offsets])
    axis.set_yticks(range(len(region_season_names)), region_season_names)
    axis.tick_params(length=0)
    axis.spines[:].set_color(GRID_COLOUR)
    axis.set_title(title, loc="left", fontsize="medium", fontweight="bold")


if __name__ == "__main__":
    main()
