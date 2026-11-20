"""Score SEAS5 and IOD alerts side by side and combined, on the seasons that have both."""

from enum import StrEnum

import numpy as np
import pandas as pd
from analysis.drought_hindcast.calculate_iod_skill import (
    get_index_towards_drought,
    load_scorable_iod_cases,
    POOLED_IOD_REGION_SEASONS,
)
from analysis.drought_hindcast.calculate_skill import (
    BOOTSTRAP_SEED,
    CHANCE_PROBABILITY_DECIMALS,
    CHANCE_SIGNIFICANCE_LEVEL,
    load_scorable_cases,
    SCORE_DECIMALS,
    to_booleans,
)
from analysis.drought_hindcast.compare_with_skill_review import (
    calculate_roc_area,
    get_measured_level,
    SkillLevel,
)
from analysis.drought_hindcast.definitions import (
    DEFAULT_PROBABILITY_THRESHOLD,
    get_observed_drought_column,
)
from analysis.drought_hindcast.indicator_data import (
    INDICATOR_CASES_FILE,
    INDICATOR_COMBINATIONS_FILE,
    INDICATOR_RELIABLE_LEAD_TIMES_FILE,
)
from analysis.drought_hindcast.indicator_definitions import (
    get_iod_alert_column,
    get_iod_region_seasons,
    Indicator,
    MAIN_IOD_ALERT_RULE,
    MAIN_IOD_INDEX_MONTH_COUNT,
    MAIN_IOD_SOURCE,
)
from analysis.drought_hindcast.indicator_scoring import score_alert
from analysis.drought_hindcast.plot_countries import get_first_reliable_lead_time
from analysis.drought_hindcast.plot_skill import DEFAULT_DROUGHT_DEFINITION
from analysis.drought_hindcast.plot_thresholds import (
    count_dry_members,
    get_minimum_dry_member_counts,
)


class Combination(StrEnum):
    """When a set of indicators gives an alert."""

    SEAS5 = "seas5"
    IOD = "iod"
    EITHER = "either"
    BOTH = "both"
    # Every indicator that has skill for that region-season and lead time must alert;
    # an indicator without skill there is ignored, and without any there is no alert.
    ALL_WITH_SKILL = "all_with_skill"
    # SEAS5 alone at another threshold, to compare "either" and "both" with: a combination
    # also changes how often there is an alert.
    SEAS5_AT_LOWER_THRESHOLD = "seas5_at_lower_threshold"
    SEAS5_AT_HIGHER_THRESHOLD = "seas5_at_higher_threshold"


SEAS5_THRESHOLDS: dict[Combination, float] = {
    Combination.SEAS5: DEFAULT_PROBABILITY_THRESHOLD,
    Combination.SEAS5_AT_LOWER_THRESHOLD: 0.3,
    Combination.SEAS5_AT_HIGHER_THRESHOLD: 0.5,
}
COMBINED_INDICATORS = (Indicator.SEAS5, Indicator.IOD)
SINGLE_INDICATORS: dict[Combination, Indicator] = {
    Combination.SEAS5: Indicator.SEAS5,
    Combination.IOD: Indicator.IOD,
}
CASE_KEYS = ["region_season", "season_year", "months_until_season_start"]
IS_DROUGHT_COLUMN = "is_drought"
# The value of each indicator that is higher when a drought is more likely.
SCORE_COLUMNS: dict[Indicator, str] = {
    Indicator.SEAS5: "seas5_probability_below_lower_tercile",
    Indicator.IOD: "iod_index_towards_drought",
}
INDICATORS_WITH_SKILL_COLUMN = "indicators_with_skill"
INDICATOR_SEPARATOR = "+"


def main() -> None:
    cases = add_combinations(load_indicator_cases())
    cases.to_csv(INDICATOR_CASES_FILE, index=False)
    print(f"Wrote {len(cases)} rows to {INDICATOR_CASES_FILE}")

    random_generator = np.random.default_rng(BOOTSTRAP_SEED)
    pooled_names = [
        region_season.name
        for region_season in get_iod_region_seasons()
        if region_season.is_in_pooled_results
    ]
    cases_by_scope = {
        POOLED_IOD_REGION_SEASONS: cases.loc[cases["region_season"].isin(pooled_names)],
        **{
            str(region_season): region_season_cases
            for region_season, region_season_cases in cases.groupby(
                "region_season", sort=False
            )
        },
    }
    rows = [
        {"scope": scope_name, **scores}
        for scope_name, scope_cases in cases_by_scope.items()
        for scores in score_combinations(
            scope_cases,
            is_one_region_season=scope_name != POOLED_IOD_REGION_SEASONS,
            random_generator=random_generator,
        )
    ]
    combinations = pd.DataFrame(rows)
    combinations.to_csv(INDICATOR_COMBINATIONS_FILE, index=False)
    print(f"Wrote {len(combinations)} rows to {INDICATOR_COMBINATIONS_FILE}")
    reliable_lead_times = summarise_reliable_lead_times(combinations)
    reliable_lead_times.to_csv(INDICATOR_RELIABLE_LEAD_TIMES_FILE, index=False)
    print(
        f"Wrote {len(reliable_lead_times)} rows to {INDICATOR_RELIABLE_LEAD_TIMES_FILE}"
    )
    _print_results(combinations)


def load_indicator_cases() -> pd.DataFrame:
    """One row per season and lead time that has a SEAS5 forecast, an IOD index and an outcome."""
    seas5_cases = load_scorable_cases()
    dry_member_counts = count_dry_members(seas5_cases)
    member_counts = seas5_cases["member_count"].to_numpy()
    iod_cases = load_scorable_iod_cases()
    iod_cases = iod_cases.loc[
        (iod_cases["iod_source"] == MAIN_IOD_SOURCE.value)
        & (iod_cases["index_month_count"] == MAIN_IOD_INDEX_MONTH_COUNT)
    ]
    seas5 = pd.DataFrame(
        {
            **{key: seas5_cases[key] for key in CASE_KEYS},
            "observed_rainfall_mm": seas5_cases["observed_rainfall_mm"],
            IS_DROUGHT_COLUMN: to_booleans(
                seas5_cases, get_observed_drought_column(DEFAULT_DROUGHT_DEFINITION)
            ),
            SCORE_COLUMNS[Indicator.SEAS5]: seas5_cases[
                "probability_below_lower_tercile"
            ],
            **{
                combination.value: dry_member_counts
                >= get_minimum_dry_member_counts(threshold, member_counts)
                for combination, threshold in SEAS5_THRESHOLDS.items()
            },
        }
    )
    iod = pd.DataFrame(
        {
            **{key: iod_cases[key] for key in CASE_KEYS},
            "iod_index": iod_cases["iod_index"],
            SCORE_COLUMNS[Indicator.IOD]: get_index_towards_drought(iod_cases),
            Combination.IOD.value: to_booleans(
                iod_cases, get_iod_alert_column(MAIN_IOD_ALERT_RULE)
            ),
        }
    )
    return seas5.merge(iod, on=CASE_KEYS, validate="one_to_one")


def add_combinations(cases: pd.DataFrame) -> pd.DataFrame:
    """Adds the alerts that combine indicators, and which indicators have skill for the case."""
    groups = []
    for _, group in cases.groupby(
        ["region_season", "months_until_season_start"], sort=False
    ):
        indicators_with_skill = [
            indicator
            for indicator in COMBINED_INDICATORS
            if has_skill(group[SCORE_COLUMNS[indicator]], group[IS_DROUGHT_COLUMN])
        ]
        alerts = combine_alerts(
            {
                indicator: group[indicator.value].to_numpy()
                for indicator in COMBINED_INDICATORS
            },
            indicators_with_skill,
        )
        groups.append(
            group.assign(
                **{
                    combination.value: is_alert
                    for combination, is_alert in alerts.items()
                },
                **{
                    INDICATORS_WITH_SKILL_COLUMN: INDICATOR_SEPARATOR.join(
                        indicators_with_skill
                    )
                },
            )
        )
    return pd.concat(groups, ignore_index=True)


def has_skill(scores: pd.Series, is_drought: pd.Series) -> bool:
    """Whether the indicator reaches the skill review's bar for Include."""
    roc_area, probability_by_chance = calculate_roc_area(
        scores.to_numpy(), is_drought.to_numpy()
    )
    return get_measured_level(roc_area, probability_by_chance) == SkillLevel.INCLUDE


def combine_alerts(
    alerts_by_indicator: dict[Indicator, np.ndarray],
    indicators_with_skill: list[Indicator],
) -> dict[Combination, np.ndarray]:
    is_seas5_alert = alerts_by_indicator[Indicator.SEAS5]
    is_iod_alert = alerts_by_indicator[Indicator.IOD]
    return {
        Combination.EITHER: is_seas5_alert | is_iod_alert,
        Combination.BOTH: is_seas5_alert & is_iod_alert,
        Combination.ALL_WITH_SKILL: np.logical_and.reduce(
            [alerts_by_indicator[indicator] for indicator in indicators_with_skill]
            or [np.zeros(len(is_seas5_alert), dtype=bool)]
        ),
    }


def score_combinations(
    cases: pd.DataFrame,
    is_one_region_season: bool,
    random_generator: np.random.Generator,
) -> list[dict[str, str | int | float | None]]:
    """Scores per lead time and combination; the ROC area only for a single indicator."""
    rows: list[dict[str, str | int | float | None]] = []
    for months_until_season_start, lead_cases in cases.groupby(
        "months_until_season_start"
    ):
        is_drought = lead_cases[IS_DROUGHT_COLUMN].to_numpy()
        for combination in Combination:
            indicator = SINGLE_INDICATORS.get(combination)
            roc_area, roc_area_probability_by_chance = (
                calculate_roc_area(
                    lead_cases[SCORE_COLUMNS[indicator]].to_numpy(), is_drought
                )
                if indicator is not None
                else (None, None)
            )
            rows.append(
                {
                    "months_until_season_start": int(months_until_season_start),
                    "combination": combination.value,
                    **score_alert(
                        is_alert=lead_cases[combination.value].to_numpy(),
                        is_drought=is_drought,
                        season_years=lead_cases["season_year"].to_numpy(),
                        is_one_region_season=is_one_region_season,
                        random_generator=random_generator,
                    ),
                    "roc_area": (
                        None if roc_area is None else round(roc_area, SCORE_DECIMALS)
                    ),
                    "roc_area_probability_by_chance": (
                        round(
                            roc_area_probability_by_chance, CHANCE_PROBABILITY_DECIMALS
                        )
                        if roc_area_probability_by_chance is not None
                        and is_one_region_season
                        else None
                    ),
                    INDICATORS_WITH_SKILL_COLUMN: (
                        lead_cases[INDICATORS_WITH_SKILL_COLUMN].iloc[0]
                        if is_one_region_season
                        else None
                    ),
                    "correlation_between_indicators": (
                        round(
                            lead_cases[SCORE_COLUMNS[Indicator.SEAS5]].corr(
                                lead_cases[SCORE_COLUMNS[Indicator.IOD]]
                            ),
                            SCORE_DECIMALS,
                        )
                        if is_one_region_season
                        else None
                    ),
                }
            )
    return rows


def summarise_reliable_lead_times(combinations: pd.DataFrame) -> pd.DataFrame:
    """Per region-season and combination, the earliest forecast from which the alerts beat
    chance at every later forecast too, with the scores at that forecast.

    The same measure as in plot_countries. Without such a forecast, the scores at the
    season start are given.
    """
    rows = []
    for (scope, combination), scores in combinations.loc[
        combinations["scope"] != POOLED_IOD_REGION_SEASONS
    ].groupby(["scope", "combination"], sort=False):
        scores = scores.set_index("months_until_season_start")
        reliable_from = get_first_reliable_lead_time(
            (scores["probability_by_chance"] < CHANCE_SIGNIFICANCE_LEVEL).to_dict()
        )
        scores_shown = scores.loc[reliable_from if reliable_from is not None else 0]
        rows.append(
            {
                "region_season": scope,
                "combination": combination,
                "reliable_from_months_before_season": reliable_from,
                "hit_count": int(scores_shown["hit_count"]),
                "drought_count": int(scores_shown["drought_count"]),
                "alert_count": int(scores_shown["alert_count"]),
                "hit_rate": scores_shown["hit_rate"],
                "false_alarm_ratio": scores_shown["false_alarm_ratio"],
            }
        )
    return pd.DataFrame(rows).astype({"reliable_from_months_before_season": "Int64"})


def _print_results(combinations: pd.DataFrame) -> None:
    for measure in ("hit_rate", "false_alarm_ratio"):
        print(f"{measure}, by months until the season starts:")
        print(
            combinations.pivot(
                index=["scope", "combination"],
                columns="months_until_season_start",
                values=measure,
            )
            .sort_index(axis="columns", ascending=False)
            .to_string()
        )


if __name__ == "__main__":
    main()
