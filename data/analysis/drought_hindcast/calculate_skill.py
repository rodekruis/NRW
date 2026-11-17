"""Score the alerts against observed droughts, per lead time, alert rule and region-season."""

import numpy as np
import pandas as pd
from analysis.drought_hindcast.definitions import (
    AREA_RULE_ALERT_COLUMN,
    DROUGHT_DEFINITIONS,
    ForecastVariant,
    get_observed_drought_column,
    get_probability_alert_column,
    POOLED_REGION_SEASONS,
    PROBABILITY_THRESHOLDS,
)
from analysis.drought_hindcast.study_area import FORECAST_ALERTS_FILE, SKILL_FILE
from scipy.stats import hypergeom

ALL_REGION_SEASONS = "All region-seasons"
AREA_RULE_NAME = "area_rule"
ALERT_COLUMN_BY_RULE: dict[str, str] = {
    **{
        f"probability_{threshold}": get_probability_alert_column(threshold)
        for threshold in PROBABILITY_THRESHOLDS
    },
    AREA_RULE_NAME: AREA_RULE_ALERT_COLUMN,
}

BOOTSTRAP_SAMPLE_COUNT = 2000
BOOTSTRAP_SEED = 45772
UNCERTAINTY_PERCENTILES = (2.5, 97.5)
# A region-season counts as better than chance below this probability of its hits by chance.
CHANCE_SIGNIFICANCE_LEVEL = 0.05
SCORE_DECIMALS = 3
CHANCE_PROBABILITY_DECIMALS = 4


def main() -> None:
    cases = load_scorable_cases()
    random_generator = np.random.default_rng(BOOTSTRAP_SEED)
    cases_by_scope = {
        ALL_REGION_SEASONS: select_pooled_cases(cases),
        **{
            str(region_season): region_season_cases
            for region_season, region_season_cases in cases.groupby(
                "region_season", sort=False
            )
        },
    }
    rows = [
        {
            "scope": scope_name,
            "drought_definition": definition_name,
            "alert_rule": rule_name,
            **scores,
            # Left out for the pooled scope: its cases within a year are not independent.
            "probability_by_chance": (
                None
                if scope_name == ALL_REGION_SEASONS
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
        for scope_name, scope_cases in cases_by_scope.items()
        for definition_name in DROUGHT_DEFINITIONS
        for rule_name in ALERT_COLUMN_BY_RULE
        for scores in score_lead_times(
            scope_cases, definition_name, rule_name, random_generator
        )
    ]
    skill = pd.DataFrame(rows)
    skill.to_csv(SKILL_FILE, index=False)
    print(f"Wrote {len(rows)} rows to {SKILL_FILE}")
    _print_better_than_chance_counts(skill)


def load_scorable_cases() -> pd.DataFrame:
    """Forecasts issued up to the season start, for seasons that have been observed."""
    alerts = pd.read_csv(FORECAST_ALERTS_FILE)
    return alerts.loc[
        (alerts["variant"] == ForecastVariant.REST_OF_SEASON.value)
        & (alerts["months_until_season_start"] >= 0)
        & alerts["observed_rainfall_mm"].notna()
    ]


def select_pooled_cases(cases: pd.DataFrame) -> pd.DataFrame:
    return cases.loc[
        cases["region_season"].isin(
            [region_season.name for region_season in POOLED_REGION_SEASONS]
        )
    ]


def score_lead_times(
    cases: pd.DataFrame,
    definition_name: str,
    rule_name: str,
    random_generator: np.random.Generator,
) -> list[dict[str, int | float]]:
    """Scores per lead time, from the season start to the earliest run."""
    rows: list[dict[str, int | float]] = []
    for months_until_season_start in sorted(
        cases["months_until_season_start"].unique()
    ):
        lead_cases = cases.loc[
            cases["months_until_season_start"] == months_until_season_start
        ]
        covers_full_season = (
            lead_cases["forecast_month_count"] == lead_cases["season_month_count"]
        )
        rows.append(
            {
                "months_until_season_start": int(months_until_season_start),
                **calculate_scores(
                    is_alert=to_booleans(lead_cases, ALERT_COLUMN_BY_RULE[rule_name]),
                    is_drought=to_booleans(
                        lead_cases, get_observed_drought_column(definition_name)
                    ),
                    season_years=lead_cases["season_year"].to_numpy(),
                    random_generator=random_generator,
                ),
                "full_season_share": _round(covers_full_season.mean()),
            }
        )
    return rows


def to_booleans(cases: pd.DataFrame, column_name: str) -> np.ndarray:
    """Columns with empty cells are not read as booleans, so compare the text instead."""
    return (cases[column_name].astype(str) == str(True)).to_numpy()


def _print_better_than_chance_counts(skill: pd.DataFrame) -> None:
    region_seasons = skill.loc[skill["scope"] != ALL_REGION_SEASONS]
    is_pooled = region_seasons["scope"].isin(
        [region_season.name for region_season in POOLED_REGION_SEASONS]
    )
    counts = (
        region_seasons.loc[is_pooled]
        .assign(
            is_better_than_chance=lambda rows: (
                rows["probability_by_chance"] < CHANCE_SIGNIFICANCE_LEVEL
            )
        )
        .pivot_table(
            index=["drought_definition", "alert_rule"],
            columns="months_until_season_start",
            values="is_better_than_chance",
            aggfunc="sum",
        )
        .sort_index(axis="columns", ascending=False)
    )
    print(
        f"Region-seasons, out of {len(POOLED_REGION_SEASONS)}, better than chance at "
        f"{CHANCE_SIGNIFICANCE_LEVEL:.0%}, by months until the season starts:"
    )
    print(counts.to_string())


def calculate_scores(
    is_alert: np.ndarray,
    is_drought: np.ndarray,
    season_years: np.ndarray,
    random_generator: np.random.Generator,
) -> dict[str, int | float]:
    """Hit rate and false-alarm ratio, with uncertainty ranges from resampling whole years.

    Whole years are resampled because region-seasons in the same year are not independent.
    """
    is_hit = is_alert & is_drought
    _, year_positions = np.unique(season_years, return_inverse=True)
    # [year, (hits, alerts, droughts)]
    yearly_counts = np.stack(
        [
            np.bincount(year_positions, weights=counted)
            for counted in (is_hit, is_alert, is_drought)
        ],
        axis=1,
    )
    year_count = len(yearly_counts)
    # [sample, year]: how often each year is drawn
    draws = random_generator.multinomial(
        year_count, np.full(year_count, 1 / year_count), size=BOOTSTRAP_SAMPLE_COUNT
    )
    sample_hits, sample_alerts, sample_droughts = (draws @ yearly_counts).T
    hit_rate_low, hit_rate_high = _get_uncertainty_range(
        _divide(sample_hits, sample_droughts)
    )
    false_alarm_ratio_low, false_alarm_ratio_high = _get_uncertainty_range(
        1 - _divide(sample_hits, sample_alerts)
    )

    hit_count, alert_count, drought_count = (
        int(is_hit.sum()),
        int(is_alert.sum()),
        int(is_drought.sum()),
    )
    season_count = len(is_alert)
    return {
        "season_count": season_count,
        "drought_count": drought_count,
        "alert_count": alert_count,
        "hit_count": hit_count,
        "hit_rate": _round(_divide(hit_count, drought_count)),
        "hit_rate_low": hit_rate_low,
        "hit_rate_high": hit_rate_high,
        "false_alarm_ratio": _round(1 - _divide(hit_count, alert_count)),
        "false_alarm_ratio_low": false_alarm_ratio_low,
        "false_alarm_ratio_high": false_alarm_ratio_high,
        "alert_frequency": _round(alert_count / season_count),
        "drought_frequency": _round(drought_count / season_count),
    }


def calculate_probability_by_chance(
    hit_count: int, alert_count: int, drought_count: int, season_count: int
) -> float:
    """Probability of at least this many hits if the alerts were unrelated to the droughts.

    One-sided Fisher exact test: the same number of alerts spread at random over the
    seasons, which are treated as independent.
    """
    return float(hypergeom.sf(hit_count - 1, season_count, drought_count, alert_count))


def _divide(
    numerator: np.ndarray | float, denominator: np.ndarray | float
) -> np.ndarray:
    """Division that gives NaN where there is nothing to divide by."""
    numerator = np.asarray(numerator, dtype=float)
    denominator = np.asarray(denominator, dtype=float)
    return np.divide(
        numerator,
        denominator,
        out=np.full(np.broadcast(numerator, denominator).shape, np.nan),
        where=denominator > 0,
    )


def _get_uncertainty_range(sample_scores: np.ndarray) -> tuple[float, float]:
    if np.isnan(sample_scores).all():
        return np.nan, np.nan
    low, high = np.nanpercentile(sample_scores, UNCERTAINTY_PERCENTILES)
    return _round(low), _round(high)


def _round(value: np.ndarray | float) -> float:
    return round(float(value), SCORE_DECIMALS)


if __name__ == "__main__":
    main()
