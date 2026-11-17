"""Score the FEWS NET alerts against observed droughts, next to SEAS5 on the same seasons."""

import numpy as np
import pandas as pd
from analysis.drought_hindcast.calculate_fews_net_alerts import (
    CHANGE_RANK_COLUMN,
    SHARE_RANK_COLUMN,
)
from analysis.drought_hindcast.calculate_skill import (
    BOOTSTRAP_SEED,
    load_scorable_cases,
    to_booleans,
)
from analysis.drought_hindcast.combine_indicators import CASE_KEYS, Combination
from analysis.drought_hindcast.definitions import (
    DEFAULT_PROBABILITY_THRESHOLD,
    DROUGHT_DEFINITIONS,
    get_observed_drought_column,
    get_probability_alert_column,
    REGION_SEASONS,
)
from analysis.drought_hindcast.indicator_data import (
    FEWS_NET_ALERTS_FILE,
    FEWS_NET_SKILL_FILE,
)
from analysis.drought_hindcast.indicator_definitions import (
    FEWS_NET_MINIMUM_SEASON_COUNT,
    FewsNetAlertRule,
    get_fews_net_alert_column,
    Indicator,
    MAIN_FEWS_NET_ALERT_RULE,
    MAIN_FEWS_NET_REPORT_LAG_MONTHS,
)
from analysis.drought_hindcast.indicator_scoring import (
    measure_discrimination,
    score_alert,
    Scores,
)
from analysis.drought_hindcast.plot_skill import (
    DEFAULT_DROUGHT_DEFINITION,
    DEFAULT_RULE,
)

POOLED_FEWS_NET_REGION_SEASONS = "Pooled FEWS NET region-seasons"
SEAS5_ALERT_COLUMN = get_probability_alert_column(DEFAULT_PROBABILITY_THRESHOLD)
SEAS5_PROBABILITY_COLUMN = "probability_below_lower_tercile"
# The value behind each rule, as its rank among the region's other years, so that it
# can be compared between regions.
RANK_COLUMNS: dict[FewsNetAlertRule, str] = {
    FewsNetAlertRule.OWN_TERCILE: SHARE_RANK_COLUMN,
    FewsNetAlertRule.FIXED_SHARE: SHARE_RANK_COLUMN,
    FewsNetAlertRule.WORSENING: CHANGE_RANK_COLUMN,
}


def main() -> None:
    cases = load_scorable_fews_net_cases()
    random_generator = np.random.default_rng(BOOTSTRAP_SEED)
    rows = [
        {
            "scope": scope_name,
            "report_lag_months": report_lag_months,
            "drought_definition": definition_name,
            "months_until_season_start": months_until_season_start,
            **scores,
        }
        for report_lag_months, lag_cases in cases.groupby("report_lag_months")
        for scope_name, scope_cases in _split_by_scope(lag_cases).items()
        for definition_name in DROUGHT_DEFINITIONS
        for months_until_season_start, lead_cases in scope_cases.groupby(
            "months_until_season_start"
        )
        for scores in score_lead_time(
            lead_cases,
            definition_name,
            is_one_region_season=scope_name != POOLED_FEWS_NET_REGION_SEASONS,
            random_generator=random_generator,
        )
    ]
    skill = pd.DataFrame(rows)
    skill.to_csv(FEWS_NET_SKILL_FILE, index=False)
    print(f"Wrote {len(skill)} rows to {FEWS_NET_SKILL_FILE}")
    _print_main_results(skill)


def load_scorable_fews_net_cases() -> pd.DataFrame:
    """FEWS NET alerts for observed seasons, with the SEAS5 forecast of the same run.

    Region-seasons with too few seasons are left out.
    """
    alerts = pd.read_csv(FEWS_NET_ALERTS_FILE)
    alerts = alerts.loc[alerts["observed_rainfall_mm"].notna()]
    cases = alerts.merge(
        load_scorable_cases()[
            [*CASE_KEYS, SEAS5_PROBABILITY_COLUMN, SEAS5_ALERT_COLUMN]
        ],
        on=CASE_KEYS,
        validate="many_to_one",
    )
    season_counts = cases.groupby("region_season")["season_year"].nunique()
    too_short = season_counts.index[season_counts < FEWS_NET_MINIMUM_SEASON_COUNT]
    print(
        f"Not scored, fewer than {FEWS_NET_MINIMUM_SEASON_COUNT} seasons: "
        f"{', '.join(too_short)}"
    )
    return cases.loc[~cases["region_season"].isin(too_short)]


def score_lead_time(
    cases: pd.DataFrame,
    definition_name: str,
    is_one_region_season: bool,
    random_generator: np.random.Generator,
) -> list[dict[str, str | int | float | None]]:
    """Scores of SEAS5, of every FEWS NET rule, and of the main rule combined with SEAS5."""
    is_drought = to_booleans(cases, get_observed_drought_column(definition_name))
    season_years = cases["season_year"].to_numpy()
    is_seas5_alert = to_booleans(cases, SEAS5_ALERT_COLUMN)
    is_fews_net_alert = {
        rule: to_booleans(cases, get_fews_net_alert_column(rule))
        for rule in FewsNetAlertRule
    }
    is_main_alert = is_fews_net_alert[MAIN_FEWS_NET_ALERT_RULE]

    def score(is_alert: np.ndarray) -> Scores:
        return score_alert(
            is_alert, is_drought, season_years, is_one_region_season, random_generator
        )

    return [
        {
            "indicator": Indicator.SEAS5.value,
            "alert_rule": DEFAULT_RULE,
            **score(is_seas5_alert),
            **measure_discrimination(
                cases[SEAS5_PROBABILITY_COLUMN].to_numpy(),
                is_drought,
                is_one_region_season,
            ),
        },
        *[
            {
                "indicator": Indicator.FEWS_NET.value,
                "alert_rule": rule.value,
                **score(is_fews_net_alert[rule]),
                **_measure_rank_discrimination(
                    cases[RANK_COLUMNS[rule]].to_numpy(),
                    is_drought,
                    is_one_region_season,
                ),
            }
            for rule in FewsNetAlertRule
        ],
        {
            "indicator": Combination.EITHER.value,
            "alert_rule": MAIN_FEWS_NET_ALERT_RULE.value,
            **score(is_seas5_alert | is_main_alert),
        },
        {
            "indicator": Combination.BOTH.value,
            "alert_rule": MAIN_FEWS_NET_ALERT_RULE.value,
            **score(is_seas5_alert & is_main_alert),
        },
    ]


def _measure_rank_discrimination(
    ranks: np.ndarray, is_drought: np.ndarray, is_one_region_season: bool
) -> Scores:
    """ROC area over the seasons that have a rank; a projected change needs a current situation."""
    has_rank = ~np.isnan(ranks)
    return measure_discrimination(
        ranks[has_rank], is_drought[has_rank], is_one_region_season
    )


def _split_by_scope(cases: pd.DataFrame) -> dict[str, pd.DataFrame]:
    pooled_names = [
        region_season.name
        for region_season in REGION_SEASONS
        if region_season.is_in_pooled_results
    ]
    return {
        POOLED_FEWS_NET_REGION_SEASONS: cases.loc[
            cases["region_season"].isin(pooled_names)
        ],
        **{
            str(region_season): region_season_cases
            for region_season, region_season_cases in cases.groupby(
                "region_season", sort=False
            )
        },
    }


def _print_main_results(skill: pd.DataFrame) -> None:
    main_skill = skill.loc[
        (skill["report_lag_months"] == MAIN_FEWS_NET_REPORT_LAG_MONTHS)
        & (skill["drought_definition"] == DEFAULT_DROUGHT_DEFINITION)
        & (skill["scope"] == POOLED_FEWS_NET_REGION_SEASONS)
    ]
    print(
        f"{POOLED_FEWS_NET_REGION_SEASONS}, report of {MAIN_FEWS_NET_REPORT_LAG_MONTHS} "
        f"month before the run, {DEFAULT_DROUGHT_DEFINITION}; "
        "by months until the season starts:"
    )
    for measure in ("roc_area", "hit_rate", "false_alarm_ratio", "alert_count"):
        print(measure)
        print(
            main_skill.pivot(
                index=["indicator", "alert_rule"],
                columns="months_until_season_start",
                values=measure,
            )
            .sort_index(axis="columns", ascending=False)
            .to_string()
        )


if __name__ == "__main__":
    main()
