"""Score the forecasts that are issued within the season, under each way to account for
the season months that have passed."""

import numpy as np
import pandas as pd
from analysis.drought_hindcast.calculate_skill import (
    ALL_REGION_SEASONS,
    BOOTSTRAP_SEED,
    calculate_probability_by_chance,
    CHANCE_PROBABILITY_DECIMALS,
    score_lead_times,
    select_pooled_cases,
)
from analysis.drought_hindcast.definitions import ForecastVariant, POOLED_REGION_SEASONS
from analysis.drought_hindcast.indicator_data import IN_SEASON_SKILL_FILE
from analysis.drought_hindcast.plot_skill import (
    capitalise,
    DEFAULT_DROUGHT_DEFINITION,
    DEFAULT_RULE,
    draw_skill_panel,
    DROUGHT_DEFINITION_LABELS,
    finish_figure,
    GRID_COLOUR,
    POOLED_LABEL,
    RULE_LABELS,
)
from analysis.drought_hindcast.study_area import FORECAST_ALERTS_FILE
from matplotlib.figure import Figure

VARIANT_LABELS = {
    ForecastVariant.REST_OF_SEASON: "Forecast for the rest of the season only",
    ForecastVariant.EARLIER_FORECAST_FOR_PAST_MONTHS: (
        "Past months from earlier forecasts"
    ),
    ForecastVariant.OBSERVED_FOR_PAST_MONTHS: "Past months from observed rainfall",
}
# Every pooled region-season has at least three months, so two forecasts within it.
LAST_MONTHS_INTO_SEASON_SHOWN = 2
IN_SEASON_PANEL_SIZE_INCHES = (4.2, 3.6)
IN_SEASON_AXIS_LABEL = (
    "Months before the season starts; negative and shaded is within the season"
)


def main() -> None:
    alerts = pd.read_csv(FORECAST_ALERTS_FILE)
    cases = select_pooled_cases(alerts.loc[alerts["observed_rainfall_mm"].notna()])
    random_generator = np.random.default_rng(BOOTSTRAP_SEED)
    skill = pd.DataFrame(
        [
            {
                "scope": scope,
                "variant": variant.value,
                **scores,
                # Left out for the pooled scope: its cases within a year are not independent.
                "probability_by_chance": (
                    None
                    if scope == ALL_REGION_SEASONS
                    else round(
                        calculate_probability_by_chance(
                            hit_count=int(scores["hit_count"]),
                            alert_count=int(scores["alert_count"]),
                            drought_count=int(scores["drought_count"]),
                            season_count=int(scores["season_count"]),
                        ),
                        CHANCE_PROBABILITY_DECIMALS,
                    )
                ),
            }
            for scope, scope_cases in [
                (ALL_REGION_SEASONS, cases),
                *[
                    (
                        region_season.name,
                        cases.loc[cases["region_season"] == region_season.name],
                    )
                    for region_season in POOLED_REGION_SEASONS
                ],
            ]
            for variant in ForecastVariant
            for scores in score_lead_times(
                select_variant_cases(scope_cases, variant),
                DEFAULT_DROUGHT_DEFINITION,
                DEFAULT_RULE,
                random_generator,
            )
        ]
    )
    skill.to_csv(IN_SEASON_SKILL_FILE, index=False)
    print(f"Wrote {len(skill)} rows to {IN_SEASON_SKILL_FILE}")
    _plot_in_season(skill)


def select_variant_cases(cases: pd.DataFrame, variant: ForecastVariant) -> pd.DataFrame:
    """The forecasts up to the season start, which are the same for every variant, and
    those of the variant within the season. `forecast_month_count` becomes the season
    months that the value covers, past months included.
    """
    is_before_season = (cases["months_until_season_start"] >= 0) & (
        cases["variant"] == ForecastVariant.REST_OF_SEASON.value
    )
    is_within_season = (cases["months_until_season_start"] < 0) & (
        cases["variant"] == variant.value
    )
    selected = cases.loc[is_before_season | is_within_season]
    if variant == ForecastVariant.REST_OF_SEASON:
        return selected
    return selected.assign(
        forecast_month_count=selected["forecast_month_count"]
        + selected["past_month_count"]
    )


def _plot_in_season(skill: pd.DataFrame) -> None:
    """Both measures from four months before the season to two months into it, for all
    region-seasons together: one panel per variant.
    """
    panel_width, panel_height = IN_SEASON_PANEL_SIZE_INCHES
    figure = Figure(
        figsize=(len(ForecastVariant) * panel_width, panel_height + 0.6),
        layout="constrained",
    )
    axes = figure.subplots(1, len(ForecastVariant), sharey=True)
    for axis, variant in zip(axes, ForecastVariant, strict=True):
        scores = skill.loc[
            (skill["scope"] == ALL_REGION_SEASONS)
            & (skill["variant"] == variant.value)
            & (skill["months_until_season_start"] >= -LAST_MONTHS_INTO_SEASON_SHOWN)
        ].sort_values("months_until_season_start", ascending=False)
        draw_skill_panel(axis, scores, VARIANT_LABELS[variant])
        axis.axvspan(-0.5, axis.get_xlim()[1], color=GRID_COLOUR, alpha=0.5, zorder=0)
    finish_figure(
        figure,
        f"{capitalise(POOLED_LABEL)}; {RULE_LABELS[DEFAULT_RULE].lower()}; "
        f"{DROUGHT_DEFINITION_LABELS[DEFAULT_DROUGHT_DEFINITION].lower()}",
        "skill_in_season",
        x_label=IN_SEASON_AXIS_LABEL,
    )


if __name__ == "__main__":
    main()
