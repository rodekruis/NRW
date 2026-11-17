"""Set the SEAS5 grades of the skill review (from literature) next to the skill measured
here, per region-season and issue month: the scores of the alert rule, and whether the
forecast passes the review's own bar."""

from collections.abc import Callable
from enum import StrEnum

import numpy as np
import pandas as pd
from analysis.drought_hindcast.calculate_skill import (
    ALL_REGION_SEASONS,
    CHANCE_SIGNIFICANCE_LEVEL,
    load_scorable_cases,
    select_pooled_cases,
    to_booleans,
)
from analysis.drought_hindcast.definitions import (
    DEFAULT_PROBABILITY_THRESHOLD,
    get_observed_drought_column,
    POOLED_REGION_SEASONS,
)
from analysis.drought_hindcast.plot_skill import (
    DEFAULT_DROUGHT_DEFINITION,
    DEFAULT_RULE,
    GRID_COLOUR,
    save_figure,
    select_scores,
)
from analysis.drought_hindcast.study_area import (
    SKILL_FILE,
    SKILL_REVIEW_COMPARISON_FILE,
    SKILL_REVIEW_GRADES_FILE,
)
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from scipy.stats import mannwhitneyu


class SkillLevel(StrEnum):
    """Grades of the skill review, also used for the levels that the measured skill reaches."""

    INCLUDE = "Include"
    READINESS = "Readiness"
    EXCLUDE = "Exclude"


# The review's own bar for Include: ROC area for the below-normal tercile of at least 0.6,
# and significant. Readiness: marginal skill, a ROC area between 0.5 and 0.6.
INCLUDE_MINIMUM_ROC_AREA = 0.6
READINESS_MINIMUM_ROC_AREA = 0.5
SIGNIFICANCE_LEVEL = 0.05
SCORE_DECIMALS = 3

LEVEL_COLOURS = {
    SkillLevel.INCLUDE: "#2f855a",
    SkillLevel.READINESS: "#f6c453",
    SkillLevel.EXCLUDE: "#e5e7eb",
}
DARK_TEXT_COLOUR = "#111827"
LEVEL_TEXT_COLOURS = {
    SkillLevel.INCLUDE: "white",
    SkillLevel.READINESS: DARK_TEXT_COLOUR,
    SkillLevel.EXCLUDE: DARK_TEXT_COLOUR,
}
RULE_MARKER_OFFSET = (0.34, -0.28)
RULE_MARKER_SIZE = 22
REVIEW_LEGEND_LABELS = {
    SkillLevel.INCLUDE: "Include",
    SkillLevel.READINESS: "Readiness only",
    SkillLevel.EXCLUDE: "Exclude",
}
RULE_LEGEND_LABELS = {
    SkillLevel.INCLUDE: (
        f"The alerts beat chance (below {CHANCE_SIGNIFICANCE_LEVEL:.0%} probability "
        "of as many hits by luck)"
    ),
    SkillLevel.READINESS: "Hit rate above the level without skill, but could be luck",
    SkillLevel.EXCLUDE: "Hit rate at or below the level without skill",
}
NO_ALERTS_TEXT = "-"
LEGEND_PLACEMENT = {
    "loc": "upper left",
    "bbox_to_anchor": (0, -0.08),
    "frameon": False,
    "fontsize": "small",
}
MONTH_ABBREVIATIONS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def main() -> None:
    grades = pd.read_csv(SKILL_REVIEW_GRADES_FILE)
    cases = select_pooled_cases(load_scorable_cases())
    comparison = grades.merge(
        _measure_discrimination(cases),
        on=["region_season", "months_until_season_start"],
        validate="one_to_one",
    ).merge(
        _load_alert_scores(),
        on=["region_season", "months_until_season_start"],
        validate="one_to_one",
    )
    comparison["rule_level"] = [
        get_rule_level(hit_rate, alert_frequency, probability_by_chance).value
        for hit_rate, alert_frequency, probability_by_chance in zip(
            comparison["hit_rate"],
            comparison["alert_frequency"],
            comparison["hits_probability_by_chance"],
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
    comparison.to_csv(SKILL_REVIEW_COMPARISON_FILE, index=False)
    print(f"Wrote {len(comparison)} rows to {SKILL_REVIEW_COMPARISON_FILE}")

    _print_agreement(comparison)
    _plot_comparison(comparison)


def _measure_discrimination(cases: pd.DataFrame) -> pd.DataFrame:
    """ROC area and correlation per region-season and lead time."""
    rows = []
    for (region_season, months_until_season_start), group in cases.groupby(
        ["region_season", "months_until_season_start"], sort=False
    ):
        roc_area, probability_by_chance = calculate_roc_area(
            group["probability_below_lower_tercile"].to_numpy(),
            to_booleans(group, get_observed_drought_column(DEFAULT_DROUGHT_DEFINITION)),
        )
        rows.append(
            {
                "region_season": region_season,
                "months_until_season_start": months_until_season_start,
                "roc_area": round(roc_area, SCORE_DECIMALS),
                "roc_area_probability_by_chance": round(
                    probability_by_chance, SCORE_DECIMALS + 1
                ),
                "correlation_of_ensemble_mean": round(
                    group["ensemble_mean_mm"].corr(group["observed_rainfall_mm"]),
                    SCORE_DECIMALS,
                ),
            }
        )
    return pd.DataFrame(rows)


def calculate_roc_area(
    shares_of_dry_members: np.ndarray, is_drought: np.ndarray
) -> tuple[float, float]:
    """Chance that a drought year has a larger share of dry members than another year.

    0.5 means no discrimination, 1 perfect. It needs no alert threshold. The second value
    is the probability of an area at least this large by chance (Mann-Whitney test).
    """
    drought_shares = shares_of_dry_members[is_drought]
    other_shares = shares_of_dry_members[~is_drought]
    result = mannwhitneyu(drought_shares, other_shares, alternative="greater")
    return (
        float(result.statistic) / (len(drought_shares) * len(other_shares)),
        float(result.pvalue),
    )


def get_rule_level(
    hit_rate: float, alert_frequency: float, probability_by_chance: float
) -> SkillLevel:
    """How far the alerts of the rule stand out from alerts unrelated to droughts.

    Such alerts catch as large a share of the droughts as they are frequent.
    """
    if probability_by_chance < CHANCE_SIGNIFICANCE_LEVEL:
        return SkillLevel.INCLUDE
    if hit_rate > alert_frequency:
        return SkillLevel.READINESS
    return SkillLevel.EXCLUDE


def get_measured_level(roc_area: float, probability_by_chance: float) -> SkillLevel:
    """The review's own bar, applied to the ROC area measured here."""
    if (
        roc_area >= INCLUDE_MINIMUM_ROC_AREA
        and probability_by_chance < SIGNIFICANCE_LEVEL
    ):
        return SkillLevel.INCLUDE
    if roc_area > READINESS_MINIMUM_ROC_AREA:
        return SkillLevel.READINESS
    return SkillLevel.EXCLUDE


def _load_alert_scores() -> pd.DataFrame:
    """Hit rate and false-alarm ratio of the default rule, per region-season."""
    skill = pd.read_csv(SKILL_FILE)
    skill = skill.loc[skill["scope"] != ALL_REGION_SEASONS]
    scores = pd.concat(
        [
            select_scores(
                skill, region_season.name, DEFAULT_RULE, DEFAULT_DROUGHT_DEFINITION
            )
            for region_season in POOLED_REGION_SEASONS
        ]
    )
    return scores.rename(
        columns={
            "scope": "region_season",
            "probability_by_chance": "hits_probability_by_chance",
        }
    )[
        [
            "region_season",
            "months_until_season_start",
            "drought_count",
            "alert_count",
            "hit_count",
            "hit_rate",
            "false_alarm_ratio",
            "alert_frequency",
            "hits_probability_by_chance",
        ]
    ]


def _print_agreement(comparison: pd.DataFrame) -> None:
    print("Grade in the skill review (rows) against the level of the rule (columns):")
    levels = [level.value for level in SkillLevel]
    counts = pd.crosstab(
        comparison["grade"], comparison["rule_level"], margins=True
    ).reindex(index=[*levels, "All"], columns=[*levels, "All"], fill_value=0)
    passes_review_bar = comparison["roc_level"] == SkillLevel.INCLUDE.value
    counts["forecast_passes_review_bar"] = (
        passes_review_bar.groupby(comparison["grade"]).sum().reindex(levels)
    )
    counts.loc["All", "forecast_passes_review_bar"] = passes_review_bar.sum()
    print(counts.astype(int).to_string())


def _plot_comparison(comparison: pd.DataFrame) -> None:
    """Two grids of region-season by lead time: the review's grade, and what we measure."""
    figure = Figure(figsize=(12.5, 6.3), layout="constrained")
    review_axis, measured_axis = figure.subplots(1, 2, sharey=True)
    _draw_grid(
        review_axis,
        comparison,
        get_text=lambda row: MONTH_ABBREVIATIONS[int(row["issue_month"]) - 1],
        level_column="grade",
        title="Skill review: grade of SEAS5 per issue month",
    )
    review_axis.legend(
        handles=_create_level_patches(REVIEW_LEGEND_LABELS),
        **LEGEND_PLACEMENT,
    )
    _draw_grid(
        measured_axis,
        comparison,
        get_text=_format_rule_scores,
        level_column="rule_level",
        title=(
            f"This analysis: hit rate / false-alarm ratio (%) of the "
            f"{DEFAULT_PROBABILITY_THRESHOLD:.0%} rule"
        ),
        has_marker=lambda row: row["roc_level"] == SkillLevel.INCLUDE.value,
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
                    "The forecast passes the review's own bar: ROC area at least "
                    f"{INCLUDE_MINIMUM_ROC_AREA}, unlikely by chance"
                ),
            ),
        ],
        **LEGEND_PLACEMENT,
    )
    figure.supxlabel("Months before the season starts", fontsize="medium")
    save_figure(figure, "skill_review_comparison")


def _format_rule_scores(row: pd.Series) -> str:
    """Hit rate and false-alarm ratio in percent; the ratio is undefined without alerts."""
    false_alarm_ratio = (
        NO_ALERTS_TEXT
        if pd.isna(row["false_alarm_ratio"])
        else f"{row['false_alarm_ratio'] * 100:.0f}"
    )
    return f"{row['hit_rate'] * 100:.0f} / {false_alarm_ratio}"


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
    has_marker: Callable[[pd.Series], bool] | None = None,
) -> None:
    region_season_names = [
        region_season.name for region_season in POOLED_REGION_SEASONS
    ]
    lead_times = sorted(comparison["months_until_season_start"].unique(), reverse=True)
    for _, row in comparison.iterrows():
        level = SkillLevel(row[level_column])
        column = lead_times.index(row["months_until_season_start"])
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
            fontsize="small",
            color=LEVEL_TEXT_COLOURS[level],
        )
        if has_marker is not None and has_marker(row):
            marker_column_offset, marker_row_offset = RULE_MARKER_OFFSET
            # One colour on every cell, with a light edge so that it shows on dark cells.
            axis.scatter(
                column + marker_column_offset,
                row_position + marker_row_offset,
                s=RULE_MARKER_SIZE,
                color=DARK_TEXT_COLOUR,
                edgecolor="white",
                linewidth=0.8,
                zorder=3,
            )
    axis.set_xlim(-0.5, len(lead_times) - 0.5)
    axis.set_ylim(len(region_season_names) - 0.5, -0.5)
    axis.set_xticks(range(len(lead_times)), lead_times)
    axis.set_yticks(range(len(region_season_names)), region_season_names)
    axis.tick_params(length=0)
    axis.spines[:].set_color(GRID_COLOUR)
    axis.set_title(title, loc="left", fontsize="medium", fontweight="bold")


if __name__ == "__main__":
    main()
