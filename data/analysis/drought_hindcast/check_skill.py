"""Sanity checks on the skill scores: the cases behind them, and what shuffling or splitting
the years does to them."""

import math

import numpy as np
import pandas as pd
from analysis.drought_hindcast.calculate_skill import (
    ALERT_COLUMN_BY_RULE,
    BOOTSTRAP_SEED,
    load_scorable_cases,
    score_lead_times,
    select_pooled_cases,
    to_booleans,
    UNCERTAINTY_PERCENTILES,
)
from analysis.drought_hindcast.definitions import (
    DEFAULT_PROBABILITY_THRESHOLD,
    get_observed_drought_column,
    POOLED_REGION_SEASONS,
    REFERENCE_LAST_YEAR,
)
from analysis.drought_hindcast.plot_skill import (
    CHIP_MONTHS_BEFORE_SEASON,
    DEFAULT_DROUGHT_DEFINITION,
    DEFAULT_RULE,
    draw_skill_panel,
    DROUGHT_DEFINITION_LABELS,
    FALSE_ALARM_RATIO_COLOUR,
    finish_figure,
    get_binomial_range,
    HIT_RATE_COLOUR,
    MEASURE_COLOURS,
    MEASURE_LABELS,
    NEUTRAL_COLOUR,
    POOLED_LABEL,
    RULE_LABELS,
    save_figure,
    style_percent_axis,
)
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

SHUFFLE_COUNT = 5000
SHUFFLE_BAND_OPACITY = 0.2
NEITHER_COLOUR = "#d1d5db"
CASE_MARKER_SIZE = 60
CASES_FIGURE_WIDTH_INCHES = 12.5
CASES_FIGURE_MARGIN_INCHES = 1.4
CASES_ROW_HEIGHT_INCHES = 0.31
YEAR_TICK_STEP = 5
SEASON_YEAR_AXIS_LABEL = "Season year (the year in which the season starts)"
DESCRIPTION = (
    f"{RULE_LABELS[DEFAULT_RULE]}; "
    f"{DROUGHT_DEFINITION_LABELS[DEFAULT_DROUGHT_DEFINITION].lower()}"
)


def main() -> None:
    cases = add_outcomes(select_pooled_cases(load_scorable_cases()))
    random_generator = np.random.default_rng(BOOTSTRAP_SEED)

    plot_cases_by_year(
        cases,
        [region_season.name for region_season in POOLED_REGION_SEASONS],
        "cases_by_year",
    )
    _plot_shuffled_years(cases, random_generator)
    _plot_by_period(cases, random_generator)
    _print_sample_size(cases, random_generator)
    _print_alerts_decided_by_one_member(cases)
    _print_correlations_without_trend(cases)


def add_outcomes(cases: pd.DataFrame) -> pd.DataFrame:
    """Alert and drought under the default rule and drought definition, as booleans."""
    return cases.assign(
        is_alert=to_booleans(cases, ALERT_COLUMN_BY_RULE[DEFAULT_RULE]),
        is_drought=to_booleans(
            cases, get_observed_drought_column(DEFAULT_DROUGHT_DEFINITION)
        ),
    )


def _select_lead_time(cases: pd.DataFrame, months_before_season: int) -> pd.DataFrame:
    return cases.loc[cases["months_until_season_start"] == months_before_season]


def plot_cases_by_year(
    cases: pd.DataFrame,
    region_season_names: list[str],
    file_name: str,
    year_axis_label: str = SEASON_YEAR_AXIS_LABEL,
    description: str = DESCRIPTION,
    shows_counts: bool = True,
) -> None:
    """Every scored season of the region-seasons, marked by its outcome one month ahead."""
    cases = _select_lead_time(cases, CHIP_MONTHS_BEFORE_SEASON)
    cases = cases.loc[cases["region_season"].isin(region_season_names)]
    row_by_region_season = {
        region_season_name: row
        for row, region_season_name in enumerate(region_season_names)
    }
    outcomes = {
        "Drought with alert (hit)": (
            cases["is_drought"] & cases["is_alert"],
            {"facecolor": HIT_RATE_COLOUR, "edgecolor": HIT_RATE_COLOUR},
        ),
        "Drought without alert (miss)": (
            cases["is_drought"] & ~cases["is_alert"],
            {"facecolor": "white", "edgecolor": HIT_RATE_COLOUR},
        ),
        "Alert without drought (false alarm)": (
            ~cases["is_drought"] & cases["is_alert"],
            {
                "facecolor": FALSE_ALARM_RATIO_COLOUR,
                "edgecolor": FALSE_ALARM_RATIO_COLOUR,
            },
        ),
        "Neither": (
            ~cases["is_drought"] & ~cases["is_alert"],
            {"facecolor": NEITHER_COLOUR, "edgecolor": NEITHER_COLOUR},
        ),
    }

    figure = Figure(
        figsize=(
            CASES_FIGURE_WIDTH_INCHES,
            CASES_FIGURE_MARGIN_INCHES
            + len(region_season_names) * CASES_ROW_HEIGHT_INCHES,
        ),
        layout="constrained",
    )
    axis = figure.subplots()
    for label, (is_outcome, colours) in outcomes.items():
        axis.scatter(
            cases.loc[is_outcome, "season_year"],
            cases.loc[is_outcome, "region_season"].map(row_by_region_season),
            marker="s",
            s=CASE_MARKER_SIZE,
            linewidth=1.5,
            label=f"{label}: {is_outcome.sum()}" if shows_counts else label,
            **colours,
        )
    years = cases["season_year"]
    axis.set_xticks(
        range(
            math.ceil(years.min() / YEAR_TICK_STEP) * YEAR_TICK_STEP,
            years.max() + 1,
            YEAR_TICK_STEP,
        )
    )
    axis.set_xlim(years.min() - 1, years.max() + 1)
    axis.set_yticks(list(row_by_region_season.values()), list(row_by_region_season))
    axis.set_ylim(len(row_by_region_season) - 0.4, -0.6)
    axis.spines[["top", "right", "left"]].set_visible(False)
    axis.tick_params(length=0)
    axis.set_xlabel(year_axis_label)
    month_word = "month" if CHIP_MONTHS_BEFORE_SEASON == 1 else "months"
    figure.legend(
        title=(
            f"{description}; forecast {CHIP_MONTHS_BEFORE_SEASON} {month_word} "
            "before the season"
        ),
        alignment="left",
        loc="outside upper left",
        ncols=len(outcomes),
        frameon=False,
        fontsize="small",
    )
    save_figure(figure, file_name)


def _plot_shuffled_years(
    cases: pd.DataFrame, random_generator: np.random.Generator
) -> None:
    """The scores against what is left of them when alerts meet the droughts of other years."""
    rows = []
    for months_before_season in sorted(cases["months_until_season_start"].unique()):
        lead_cases = _select_lead_time(cases, months_before_season)
        # [year, region-season], NaN where a season is not scored
        is_alert, is_drought = (
            lead_cases.pivot(
                index="season_year", columns="region_season", values=column
            ).to_numpy(dtype=float)
            for column in ("is_alert", "is_drought")
        )
        actual = calculate_measures(is_alert, is_drought[np.newaxis])
        shuffled_years = random_generator.permuted(
            np.tile(np.arange(len(is_drought)), (SHUFFLE_COUNT, 1)), axis=1
        )
        # Whole years move, so that region-seasons keep the droughts they share.
        shuffled = calculate_measures(is_alert, is_drought[shuffled_years])
        row: dict[str, float] = {"months_until_season_start": months_before_season}
        for measure in MEASURE_LABELS:
            low, high = np.percentile(shuffled[measure], UNCERTAINTY_PERCENTILES)
            row |= {
                measure: actual[measure][0],
                f"{measure}_shuffled_low": low,
                f"{measure}_shuffled_high": high,
            }
        row["shuffles_with_as_many_hits"] = int(
            (shuffled["hit_rate"] >= actual["hit_rate"][0]).sum()
        )
        rows.append(row)
    scores = pd.DataFrame(rows)
    print(f"Scores against {SHUFFLE_COUNT} shuffles of the years:")
    print(scores.round(3).to_string(index=False))

    figure = Figure(figsize=(7.5, 6), layout="constrained")
    axis = figure.subplots()
    months = scores["months_until_season_start"]
    for measure, colour in MEASURE_COLOURS.items():
        axis.fill_between(
            months,
            scores[f"{measure}_shuffled_low"],
            scores[f"{measure}_shuffled_high"],
            color=colour,
            alpha=SHUFFLE_BAND_OPACITY,
            linewidth=0,
        )
        axis.plot(months, scores[measure], color=colour, linewidth=2, marker="o")
    _style_lead_time_axis(axis, months, POOLED_LABEL.capitalize())
    low_percentile, high_percentile = UNCERTAINTY_PERCENTILES
    figure.legend(
        handles=[
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
            Patch(
                facecolor=NEUTRAL_COLOUR,
                alpha=SHUFFLE_BAND_OPACITY * 2,
                label=(
                    f"{high_percentile - low_percentile:.0f}% of {SHUFFLE_COUNT:,} "
                    "shuffles of the years"
                ),
            ),
        ],
        title=DESCRIPTION,
        alignment="left",
        loc="outside upper left",
        ncols=2,
        frameon=False,
        fontsize="small",
    )
    save_figure(figure, "skill_with_shuffled_years")


def calculate_measures(
    is_alert: np.ndarray, is_drought: np.ndarray
) -> dict[str, np.ndarray]:
    """is_alert is [year, region-season]; is_drought and the results have a leading axis."""
    is_scored = ~np.isnan(is_alert) & ~np.isnan(is_drought)
    hit_counts = np.where(is_scored, is_alert * is_drought, 0).sum(axis=(1, 2))
    drought_counts = np.where(is_scored, is_drought, 0).sum(axis=(1, 2))
    alert_counts = np.where(is_scored, is_alert, 0).sum(axis=(1, 2))
    return {
        "hit_rate": hit_counts / drought_counts,
        "false_alarm_ratio": 1 - hit_counts / alert_counts,
    }


def _style_lead_time_axis(axis: Axes, months: pd.Series, title: str) -> None:
    axis.set_xticks(months)
    axis.set_xlim(months.max() + 0.3, months.min() - 0.3)
    axis.set_xlabel("Months before the season starts")
    style_percent_axis(axis, title)


def _plot_by_period(cases: pd.DataFrame, random_generator: np.random.Generator) -> None:
    """The recurring chart for both halves of the period, and for hindcast and forecast years."""
    years = np.sort(cases["season_year"].unique())
    last_year_of_first_half = int(years[len(years) // 2 - 1])
    is_first_half = cases["season_year"] <= last_year_of_first_half
    is_hindcast = cases["run_year"] <= REFERENCE_LAST_YEAR
    cases_by_period = {
        f"Seasons {years[0]}-{last_year_of_first_half}": cases.loc[is_first_half],
        f"Seasons {last_year_of_first_half + 1}-{years[-1]}": cases.loc[~is_first_half],
        f"Hindcast years, to {REFERENCE_LAST_YEAR}": cases.loc[is_hindcast],
        f"Forecast years, from {REFERENCE_LAST_YEAR + 1}": cases.loc[~is_hindcast],
    }

    figure = Figure(figsize=(13.5, 5.2), layout="constrained")
    axes = figure.subplots(1, len(cases_by_period), sharey=True)
    for axis, (period, period_cases) in zip(axes, cases_by_period.items(), strict=True):
        draw_skill_panel(
            axis,
            _score(period_cases, random_generator),
            period,
            chip_months_before_season=CHIP_MONTHS_BEFORE_SEASON,
        )
    finish_figure(
        figure, f"{POOLED_LABEL.capitalize()}; {DESCRIPTION.lower()}", "skill_by_period"
    )


def _score(cases: pd.DataFrame, random_generator: np.random.Generator) -> pd.DataFrame:
    return pd.DataFrame(
        score_lead_times(
            cases, DEFAULT_DROUGHT_DEFINITION, DEFAULT_RULE, random_generator
        )
    ).sort_values("months_until_season_start", ascending=False)


def _print_sample_size(
    cases: pd.DataFrame, random_generator: np.random.Generator
) -> None:
    """How many independent droughts the clustered range of the hit rate stands for."""
    scores = _score(
        _select_lead_time(cases, CHIP_MONTHS_BEFORE_SEASON), random_generator
    ).iloc[0]
    hit_count, drought_count = int(scores["hit_count"]), int(scores["drought_count"])
    independent_low, independent_high = get_binomial_range(hit_count, drought_count)
    width_ratio = (independent_high - independent_low) / (
        scores["hit_rate_high"] - scores["hit_rate_low"]
    )
    print(
        f"{CHIP_MONTHS_BEFORE_SEASON} month(s) before the season: "
        f"{int(scores['season_count'])} seasons, {drought_count} droughts, "
        f"{int(scores['alert_count'])} alerts, {hit_count} hits.\n"
        f"Hit rate range {scores['hit_rate_low']:.0%}-{scores['hit_rate_high']:.0%}; "
        f"{independent_low:.0%}-{independent_high:.0%} if the droughts were independent. "
        f"The droughts count as about {drought_count * width_ratio**2:.0f} independent ones."
    )


def _print_alerts_decided_by_one_member(cases: pd.DataFrame) -> None:
    lead_cases = _select_lead_time(cases, CHIP_MONTHS_BEFORE_SEASON)
    dry_member_counts = (
        lead_cases["probability_below_lower_tercile"] * lead_cases["member_count"]
    ).round()
    # Rounded first: 0.4 x 25 members must give 10, not the next whole number.
    needed_member_counts = np.ceil(
        (DEFAULT_PROBABILITY_THRESHOLD * lead_cases["member_count"]).round(6)
    )
    is_just_alert = dry_member_counts == needed_member_counts
    is_just_no_alert = dry_member_counts == needed_member_counts - 1
    print(
        f"Of {lead_cases['is_alert'].sum()} alerts, {is_just_alert.sum()} have exactly the "
        f"number of dry members needed; {is_just_no_alert.sum()} seasons without alert are "
        "one member short."
    )


def _print_correlations_without_trend(cases: pd.DataFrame) -> None:
    """Whether forecast and observations only agree because they share a long-term trend."""
    rows = []
    for region_season, region_cases in _select_lead_time(
        cases, CHIP_MONTHS_BEFORE_SEASON
    ).groupby("region_season", sort=False):
        years = region_cases["season_year"].to_numpy()
        forecast = region_cases["ensemble_mean_mm"].to_numpy()
        observed = region_cases["observed_rainfall_mm"].to_numpy()
        rows.append(
            {
                "region_season": region_season,
                "correlation": np.corrcoef(forecast, observed)[0, 1],
                "correlation_without_trend": np.corrcoef(
                    _remove_linear_trend(forecast, years),
                    _remove_linear_trend(observed, years),
                )[0, 1],
            }
        )
    print(
        "Correlation of the forecast ensemble mean with the observed season rainfall:"
    )
    print(pd.DataFrame(rows).round(2).to_string(index=False))


def _remove_linear_trend(values: np.ndarray, years: np.ndarray) -> np.ndarray:
    return values - np.polyval(np.polyfit(years, values, deg=1), years)


if __name__ == "__main__":
    main()
