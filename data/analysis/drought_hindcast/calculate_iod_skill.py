"""Score the IOD alerts against observed droughts, per lead time, source, rule and region-season."""

import numpy as np
import pandas as pd
from analysis.drought_hindcast.calculate_skill import (
    BOOTSTRAP_SEED,
    CHANCE_PROBABILITY_DECIMALS,
    SCORE_DECIMALS,
    to_booleans,
)
from analysis.drought_hindcast.compare_with_skill_review import calculate_roc_area
from analysis.drought_hindcast.definitions import (
    DROUGHT_DEFINITIONS,
    get_observed_drought_column,
    UPPER_TERCILE,
)
from analysis.drought_hindcast.indicator_data import IOD_ALERTS_FILE, IOD_SKILL_FILE
from analysis.drought_hindcast.indicator_definitions import (
    get_iod_alert_column,
    get_iod_region_seasons,
    IOD_PHASE_SIGNS,
    IodAlertRule,
    MAIN_IOD_ALERT_RULE,
    MAIN_IOD_INDEX_MONTH_COUNT,
    MAIN_IOD_SOURCE,
)
from analysis.drought_hindcast.indicator_scoring import (
    measure_discrimination,
    score_alert,
)
from analysis.drought_hindcast.plot_skill import DEFAULT_DROUGHT_DEFINITION

# Zimbabwe counts once in it, on its Oct-Mar season.
POOLED_IOD_REGION_SEASONS = "Pooled IOD region-seasons"


def main() -> None:
    cases = load_scorable_iod_cases()
    random_generator = np.random.default_rng(BOOTSTRAP_SEED)
    rows = [
        {
            "scope": scope_name,
            "iod_source": iod_source,
            "index_month_count": index_month_count,
            **scores,
        }
        for (iod_source, index_month_count), variant_cases in cases.groupby(
            ["iod_source", "index_month_count"], sort=False
        )
        for scope_name, scope_cases in _split_by_scope(variant_cases).items()
        for scores in score_lead_times(
            scope_cases,
            is_one_region_season=scope_name != POOLED_IOD_REGION_SEASONS,
            random_generator=random_generator,
        )
    ]
    skill = pd.DataFrame(rows)
    skill.to_csv(IOD_SKILL_FILE, index=False)
    print(f"Wrote {len(skill)} rows to {IOD_SKILL_FILE}")
    _print_main_results(skill)


def load_scorable_iod_cases() -> pd.DataFrame:
    """IOD alerts for seasons that have been observed."""
    alerts = pd.read_csv(IOD_ALERTS_FILE)
    return alerts.loc[alerts["observed_rainfall_mm"].notna()]


def get_index_towards_drought(cases: pd.DataFrame) -> np.ndarray:
    """The index with the sign that makes a higher value a more likely drought."""
    signs = cases["drought_phase"].map(
        {phase.value: sign for phase, sign in IOD_PHASE_SIGNS.items()}
    )
    return (signs * cases["iod_index"]).to_numpy()


def score_lead_times(
    cases: pd.DataFrame,
    is_one_region_season: bool,
    random_generator: np.random.Generator,
) -> list[dict[str, str | int | float | None]]:
    """Scores per drought definition, lead time and alert rule.

    The values that treat the seasons as independent or need one rainfall scale are left
    out for pooled region-seasons.
    """
    rows: list[dict[str, str | int | float | None]] = []
    for definition_name in DROUGHT_DEFINITIONS:
        for months_until_season_start, lead_cases in cases.groupby(
            "months_until_season_start"
        ):
            is_drought = to_booleans(
                lead_cases, get_observed_drought_column(definition_name)
            )
            index_towards_drought = get_index_towards_drought(lead_cases)
            discrimination = measure_discrimination(
                index_towards_drought, is_drought, is_one_region_season
            )
            season_years = lead_cases["season_year"].to_numpy()
            observed_rainfall = lead_cases["observed_rainfall_mm"].to_numpy()
            # The opposite phase against the wettest third of seasons.
            wet_roc_area, wet_roc_area_probability_by_chance = calculate_roc_area(
                -index_towards_drought,
                observed_rainfall >= np.quantile(observed_rainfall, UPPER_TERCILE),
            )
            for rule in IodAlertRule:
                rows.append(
                    {
                        "drought_definition": definition_name,
                        "alert_rule": rule.value,
                        "months_until_season_start": int(months_until_season_start),
                        **score_alert(
                            is_alert=to_booleans(
                                lead_cases, get_iod_alert_column(rule)
                            ),
                            is_drought=is_drought,
                            season_years=season_years,
                            is_one_region_season=is_one_region_season,
                            random_generator=random_generator,
                        ),
                        **discrimination,
                        "roc_area_for_wet_seasons": (
                            round(wet_roc_area, SCORE_DECIMALS)
                            if is_one_region_season
                            else None
                        ),
                        "roc_area_for_wet_seasons_probability_by_chance": (
                            round(
                                wet_roc_area_probability_by_chance,
                                CHANCE_PROBABILITY_DECIMALS,
                            )
                            if is_one_region_season
                            else None
                        ),
                        "correlation_with_rainfall": (
                            _correlate(index_towards_drought, observed_rainfall)
                            if is_one_region_season
                            else None
                        ),
                        "correlation_without_trend": (
                            _correlate(
                                _remove_linear_trend(
                                    index_towards_drought, season_years
                                ),
                                _remove_linear_trend(observed_rainfall, season_years),
                            )
                            if is_one_region_season
                            else None
                        ),
                    }
                )
    return rows


def _split_by_scope(cases: pd.DataFrame) -> dict[str, pd.DataFrame]:
    pooled_names = [
        region_season.name
        for region_season in get_iod_region_seasons()
        if region_season.is_in_pooled_results
    ]
    return {
        POOLED_IOD_REGION_SEASONS: cases.loc[cases["region_season"].isin(pooled_names)],
        **{
            str(region_season): region_season_cases
            for region_season, region_season_cases in cases.groupby(
                "region_season", sort=False
            )
        },
    }


def _correlate(first: np.ndarray, second: np.ndarray) -> float:
    return round(float(np.corrcoef(first, second)[0, 1]), SCORE_DECIMALS)


def _remove_linear_trend(values: np.ndarray, years: np.ndarray) -> np.ndarray:
    return values - np.polyval(np.polyfit(years, values, deg=1), years)


def _print_main_results(skill: pd.DataFrame) -> None:
    main_skill = skill.loc[
        (skill["iod_source"] == MAIN_IOD_SOURCE.value)
        & (skill["index_month_count"] == MAIN_IOD_INDEX_MONTH_COUNT)
        & (skill["alert_rule"] == MAIN_IOD_ALERT_RULE.value)
        & (skill["drought_definition"] == DEFAULT_DROUGHT_DEFINITION)
    ]
    print(
        f"{MAIN_IOD_SOURCE}, index of {MAIN_IOD_INDEX_MONTH_COUNT} month, "
        f"{MAIN_IOD_ALERT_RULE} rule, {DEFAULT_DROUGHT_DEFINITION}; "
        "by months until the season starts:"
    )
    for measure in ("roc_area", "hit_rate", "false_alarm_ratio"):
        print(measure)
        print(
            main_skill.pivot(
                index="scope", columns="months_until_season_start", values=measure
            )
            .sort_index(axis="columns", ascending=False)
            .to_string()
        )


if __name__ == "__main__":
    main()
