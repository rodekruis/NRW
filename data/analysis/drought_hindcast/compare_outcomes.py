"""Score SEAS5 against what FEWS NET classified after the season, next to the rainfall outcome.

It tests the outcome that the analysis is scored on, not an indicator: whether the SEAS5
alerts hold up when a drought is counted by its impact instead of its rainfall.
"""

from enum import StrEnum

import numpy as np
import pandas as pd
from analysis.drought_hindcast.calculate_fews_net_skill import (
    POOLED_FEWS_NET_REGION_SEASONS,
    SEAS5_ALERT_COLUMN,
    SEAS5_PROBABILITY_COLUMN,
)
from analysis.drought_hindcast.calculate_skill import (
    BOOTSTRAP_SEED,
    load_scorable_cases,
    to_booleans,
)
from analysis.drought_hindcast.check_fews_net import IMPACT_COLUMN
from analysis.drought_hindcast.definitions import REGION_SEASONS
from analysis.drought_hindcast.indicator_data import (
    FEWS_NET_SEASON_OUTCOMES_FILE,
    OUTCOME_SKILL_FILE,
)
from analysis.drought_hindcast.indicator_scoring import (
    measure_discrimination,
    score_alert,
)

RAINFALL_COLUMN = "is_drought"


class Outcome(StrEnum):
    """What counts as the event that an alert should have come before."""

    # The season rainfall is in the driest third of years.
    RAINFALL = "rainfall"
    # The area in Phase 3 or worse rises after the season, more than it usually does.
    IMPACT = "impact"
    RAINFALL_AND_IMPACT = "rainfall_and_impact"


def main() -> None:
    seasons = load_pooled_season_outcomes()
    print(f"{len(seasons)} seasons of {POOLED_FEWS_NET_REGION_SEASONS}:")
    print(pd.crosstab(seasons[RAINFALL_COLUMN], seasons[IMPACT_COLUMN], margins=True))

    cases = load_scorable_cases().merge(
        seasons, on=["region_season", "season_year"], validate="many_to_one"
    )
    random_generator = np.random.default_rng(BOOTSTRAP_SEED)
    skill = pd.DataFrame(
        [
            {
                "scope": POOLED_FEWS_NET_REGION_SEASONS,
                "outcome": outcome.value,
                "months_until_season_start": int(months_until_season_start),
                **score_alert(
                    is_alert=to_booleans(lead_cases, SEAS5_ALERT_COLUMN),
                    is_drought=is_event,
                    season_years=lead_cases["season_year"].to_numpy(),
                    is_one_region_season=False,
                    random_generator=random_generator,
                ),
                **measure_discrimination(
                    lead_cases[SEAS5_PROBABILITY_COLUMN].to_numpy(),
                    is_event,
                    is_one_region_season=False,
                ),
            }
            for months_until_season_start, lead_cases in cases.groupby(
                "months_until_season_start"
            )
            for outcome, is_event in get_events(lead_cases).items()
        ]
    )
    skill.to_csv(OUTCOME_SKILL_FILE, index=False)
    print(f"Wrote {len(skill)} rows to {OUTCOME_SKILL_FILE}")
    print(
        skill[
            [
                "outcome",
                "months_until_season_start",
                "season_count",
                "drought_count",
                "alert_count",
                "hit_count",
                "hit_rate",
                "false_alarm_ratio",
                "roc_area",
            ]
        ].to_string(index=False)
    )


def load_pooled_season_outcomes() -> pd.DataFrame:
    """Per season of the pooled region-seasons, the rainfall outcome and the impact outcome."""
    seasons = pd.read_csv(FEWS_NET_SEASON_OUTCOMES_FILE)
    pooled_names = [
        region_season.name
        for region_season in REGION_SEASONS
        if region_season.is_in_pooled_results
    ]
    return seasons.loc[
        seasons["region_season"].isin(pooled_names),
        ["region_season", "season_year", RAINFALL_COLUMN, IMPACT_COLUMN],
    ]


def get_events(cases: pd.DataFrame) -> dict[Outcome, np.ndarray]:
    is_dry = cases[RAINFALL_COLUMN].to_numpy(dtype=bool)
    has_impact = cases[IMPACT_COLUMN].to_numpy(dtype=bool)
    return {
        Outcome.RAINFALL: is_dry,
        Outcome.IMPACT: has_impact,
        Outcome.RAINFALL_AND_IMPACT: is_dry & has_impact,
    }


if __name__ == "__main__":
    main()
