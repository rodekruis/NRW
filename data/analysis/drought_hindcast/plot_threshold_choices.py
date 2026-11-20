"""Show what the alert threshold changes per region-season: the scores at each threshold,
how far they stand out from chance, and from which forecast an alert can be given."""

import pandas as pd
from analysis.drought_hindcast.calculate_skill import load_scorable_cases, to_booleans
from analysis.drought_hindcast.check_skill import plot_cases_by_year
from analysis.drought_hindcast.compare_with_skill_review import (
    get_rule_level,
    RULE_LEGEND_LABELS,
    SkillLevel,
)
from analysis.drought_hindcast.definitions import (
    DEFAULT_PROBABILITY_THRESHOLD,
    get_observed_drought_column,
    get_probability_alert_column,
    POOLED_REGION_SEASONS,
    PROBABILITY_THRESHOLDS,
    REGION_SEASONS,
)
from analysis.drought_hindcast.indicator_charts import (
    create_level_patches,
    draw_level_grid,
    format_scores,
)
from analysis.drought_hindcast.indicator_data import THRESHOLD_CHOICES_FILE
from analysis.drought_hindcast.plot_countries import get_first_reliable_lead_time
from analysis.drought_hindcast.plot_skill import (
    DEFAULT_DROUGHT_DEFINITION,
    draw_skill_panel,
    DROUGHT_DEFINITION_LABELS,
    finish_figure,
    LEAD_TIME_AXIS_LABEL,
    REGION_SEASON_PANEL_SIZE_INCHES,
    save_figure,
    select_scores,
)
from analysis.drought_hindcast.study_area import SKILL_FILE
from matplotlib.figure import Figure

EVIDENCE_COLUMN = "evidence_level"
SHORT_RAINS_REGION_SEASONS = ("ETH Southern OND", "KEN National OND")
GRID_FIGURE_SIZE_INCHES = (15, 5.8)
# One grid, sized for half a slide, in the words of the summary deck.
DEFAULT_GRID_FIGURE_SIZE_INCHES = (6.4, 5.2)
PLAIN_LEGEND_TITLE = "Droughts caught / false alarms (%)"
PLAIN_LEGEND_LABELS = {
    SkillLevel.INCLUDE: "Better than random alerts, with under 5% chance of luck",
    SkillLevel.READINESS: "Better than random alerts, but it could be luck",
    SkillLevel.EXCLUDE: "No better than random alerts",
}
DROUGHT_DESCRIPTION = DROUGHT_DEFINITION_LABELS[DEFAULT_DROUGHT_DEFINITION].lower()


def main() -> None:
    skill = pd.read_csv(SKILL_FILE)
    levels = add_evidence_levels(
        skill.loc[
            (skill["drought_definition"] == DEFAULT_DROUGHT_DEFINITION)
            & skill["alert_rule"].isin(
                [get_rule_name(threshold) for threshold in PROBABILITY_THRESHOLDS]
            )
        ]
    )
    choices = summarise_alert_starts(levels)
    choices.to_csv(THRESHOLD_CHOICES_FILE, index=False)
    print(f"Wrote {len(choices)} rows to {THRESHOLD_CHOICES_FILE}")
    print(
        choices.loc[choices["is_in_pooled_results"]]
        .pivot(
            index="region_season",
            columns="threshold",
            values="alert_from_months_before_season",
        )
        .to_string()
    )
    _plot_evidence_grids(
        levels,
        PROBABILITY_THRESHOLDS,
        [region_season.name for region_season in POOLED_REGION_SEASONS],
        GRID_FIGURE_SIZE_INCHES,
        legend_title=f"Hit rate / false-alarm ratio (%); {DROUGHT_DESCRIPTION}",
        legend_labels=RULE_LEGEND_LABELS,
        legend_column_count=len(RULE_LEGEND_LABELS),
        file_name="evidence_by_threshold",
    )
    _plot_evidence_grids(
        levels,
        (DEFAULT_PROBABILITY_THRESHOLD,),
        order_by_alert_start(choices, DEFAULT_PROBABILITY_THRESHOLD),
        DEFAULT_GRID_FIGURE_SIZE_INCHES,
        legend_title=PLAIN_LEGEND_TITLE,
        legend_labels=PLAIN_LEGEND_LABELS,
        legend_column_count=1,
        file_name="evidence_at_default_threshold",
    )
    _plot_short_rains_skill(skill)
    _plot_short_rains_cases()


def get_rule_name(threshold: float) -> str:
    return f"probability_{threshold}"


def add_evidence_levels(skill: pd.DataFrame) -> pd.DataFrame:
    """How far the alerts of each row stand out from alerts unrelated to droughts."""
    return skill.assign(
        **{
            EVIDENCE_COLUMN: [
                get_rule_level(hit_rate, alert_frequency, probability_by_chance).value
                for hit_rate, alert_frequency, probability_by_chance in zip(
                    skill["hit_rate"],
                    skill["alert_frequency"],
                    skill["probability_by_chance"],
                    strict=True,
                )
            ]
        }
    )


def summarise_alert_starts(levels: pd.DataFrame) -> pd.DataFrame:
    """Per region-season and threshold, the earliest forecast from which the alerts beat
    chance at every later forecast too, and the earliest from which the hit rate is at
    least above the level without skill. The scores are those at the first of the two
    that exists, or else at the season start.
    """
    rows = []
    for region_season in REGION_SEASONS:
        for threshold in PROBABILITY_THRESHOLDS:
            scores = levels.loc[
                (levels["scope"] == region_season.name)
                & (levels["alert_rule"] == get_rule_name(threshold))
            ].set_index("months_until_season_start")
            alert_from, advisory_from = find_alert_starts(
                scores[EVIDENCE_COLUMN].to_dict()
            )
            scores_shown = scores.loc[alert_from if alert_from is not None else 0]
            rows.append(
                {
                    "region_season": region_season.name,
                    "is_in_pooled_results": region_season.is_in_pooled_results,
                    "threshold": threshold,
                    "alert_from_months_before_season": alert_from,
                    "advisory_from_months_before_season": advisory_from,
                    "hit_rate": scores_shown["hit_rate"],
                    "false_alarm_ratio": scores_shown["false_alarm_ratio"],
                    "alert_frequency": scores_shown["alert_frequency"],
                    "drought_count": int(scores_shown["drought_count"]),
                }
            )
    return pd.DataFrame(rows).astype(
        {
            "alert_from_months_before_season": "Int64",
            "advisory_from_months_before_season": "Int64",
        }
    )


def find_alert_starts(
    level_by_lead_time: dict[int, str],
) -> tuple[int | None, int | None]:
    """The longest lead time from which the alerts beat chance at every later forecast
    too, and the longest from which the hit rate is above the level without skill at
    every later forecast too.
    """
    return (
        get_first_reliable_lead_time(
            {
                months_before_season: level == SkillLevel.INCLUDE.value
                for months_before_season, level in level_by_lead_time.items()
            }
        ),
        get_first_reliable_lead_time(
            {
                months_before_season: level != SkillLevel.EXCLUDE.value
                for months_before_season, level in level_by_lead_time.items()
            }
        ),
    )


def order_by_alert_start(choices: pd.DataFrame, threshold: float) -> list[str]:
    """The pooled region-seasons, from the earliest alert that beats chance to none."""
    return (
        choices.loc[
            choices["is_in_pooled_results"] & (choices["threshold"] == threshold)
        ]
        .sort_values(
            "alert_from_months_before_season",
            ascending=False,
            na_position="last",
            kind="stable",
        )["region_season"]
        .tolist()
    )


def _plot_evidence_grids(
    levels: pd.DataFrame,
    thresholds: tuple[float, ...],
    region_season_names: list[str],
    figure_size_inches: tuple[float, float],
    legend_title: str,
    legend_labels: dict[SkillLevel, str],
    legend_column_count: int,
    file_name: str,
) -> None:
    """One grid of region-season by lead time per threshold, coloured by evidence level."""
    lead_times = sorted(levels["months_until_season_start"].unique(), reverse=True)
    figure = Figure(figsize=figure_size_inches, layout="constrained")
    axes = figure.subplots(1, len(thresholds), sharey=True, squeeze=False)[0]
    for axis, threshold in zip(axes, thresholds, strict=True):
        draw_level_grid(
            axis,
            levels.loc[
                levels["scope"].isin(region_season_names)
                & (levels["alert_rule"] == get_rule_name(threshold))
            ].rename(columns={"scope": "region_season"}),
            region_season_names,
            "months_until_season_start",
            lead_times,
            get_text=format_scores,
            level_column=EVIDENCE_COLUMN,
            title=f"At least {threshold:.0%} of members dry",
        )
    figure.supxlabel(LEAD_TIME_AXIS_LABEL, fontsize="medium")
    figure.legend(
        handles=create_level_patches(legend_labels),
        title=legend_title,
        alignment="left",
        loc="outside upper left",
        ncols=legend_column_count,
        frameon=False,
        fontsize="small",
    )
    save_figure(figure, file_name)


def _plot_short_rains_skill(skill: pd.DataFrame) -> None:
    """Both measures per lead time: a row per short-rains region-season, a column per
    threshold.
    """
    panel_width, panel_height = REGION_SEASON_PANEL_SIZE_INCHES
    figure = Figure(
        figsize=(
            len(PROBABILITY_THRESHOLDS) * panel_width,
            len(SHORT_RAINS_REGION_SEASONS) * panel_height + 0.6,
        ),
        layout="constrained",
    )
    axes = figure.subplots(
        len(SHORT_RAINS_REGION_SEASONS),
        len(PROBABILITY_THRESHOLDS),
        sharex=True,
        sharey=True,
    )
    for row_axes, region_season_name in zip(
        axes, SHORT_RAINS_REGION_SEASONS, strict=True
    ):
        for axis, threshold in zip(row_axes, PROBABILITY_THRESHOLDS, strict=True):
            draw_skill_panel(
                axis,
                select_scores(
                    skill,
                    region_season_name,
                    get_rule_name(threshold),
                    DEFAULT_DROUGHT_DEFINITION,
                ),
                f"{region_season_name}, {threshold:.0%}",
            )
    finish_figure(
        figure,
        f"Share of members that must be dry for an alert; {DROUGHT_DESCRIPTION}",
        "skill_short_rains_by_threshold",
    )


def _plot_short_rains_cases() -> None:
    """The years behind the scores: a row per short-rains region-season and threshold."""
    cases = load_scorable_cases()
    is_drought = to_booleans(
        cases, get_observed_drought_column(DEFAULT_DROUGHT_DEFINITION)
    )
    rows = pd.concat(
        cases.assign(
            is_drought=is_drought,
            is_alert=to_booleans(cases, get_probability_alert_column(threshold)),
            region_season=f"{region_season_name}, {threshold:.0%}",
        ).loc[cases["region_season"] == region_season_name]
        for region_season_name in SHORT_RAINS_REGION_SEASONS
        for threshold in PROBABILITY_THRESHOLDS
    )
    plot_cases_by_year(
        rows,
        list(dict.fromkeys(rows["region_season"])),
        "cases_short_rains_by_threshold",
        description=(
            f"Share of members that must be dry for an alert; {DROUGHT_DESCRIPTION}"
        ),
        shows_counts=False,
    )


if __name__ == "__main__":
    main()
