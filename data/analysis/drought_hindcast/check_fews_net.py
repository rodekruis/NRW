"""Check FEWS NET against itself and against observed droughts after the season.

- Projections against the current situation that FEWS NET classified later, next to
  assuming that nothing changes.
- The current situation after a season against the one before it, for drought seasons
  and other seasons.
- Month by month around the end of a season, how well the latest near-term projection
  tells drought seasons apart.
"""

import numpy as np
import pandas as pd
from analysis.drought_hindcast.calculate_fews_net_alerts import (
    calculate_rank_among_others,
    CURRENT_SITUATION_SCENARIO,
    find_current_share,
    load_region_phases,
    PROJECTION_END_COLUMN,
    PROJECTION_START_COLUMN,
    REPORT_MONTH_COLUMN,
)
from analysis.drought_hindcast.calculate_fews_net_skill import (
    POOLED_FEWS_NET_REGION_SEASONS,
)
from analysis.drought_hindcast.calculate_skill import SCORE_DECIMALS, to_booleans
from analysis.drought_hindcast.definitions import (
    get_observed_drought_column,
    REGION_SEASONS,
    RegionSeason,
    UPPER_TERCILE,
)
from analysis.drought_hindcast.indicator_data import (
    FEWS_NET_AFTER_SEASON_FILE,
    FEWS_NET_AROUND_SEASON_END_FILE,
    FEWS_NET_PROJECTION_CHECK_FILE,
    FEWS_NET_SEASON_OUTCOMES_FILE,
)
from analysis.drought_hindcast.indicator_definitions import (
    FEWS_NET_MAXIMUM_CURRENT_SITUATION_AGE_MONTHS,
    FEWS_NET_MINIMUM_SEASON_COUNT,
)
from analysis.drought_hindcast.indicator_scoring import measure_discrimination
from analysis.drought_hindcast.plot_skill import DEFAULT_DROUGHT_DEFINITION
from analysis.drought_hindcast.prepare_fews_net import (
    CRISIS_OR_WORSE_COLUMN,
    OUTPUT_FLOAT_FORMAT,
)
from analysis.drought_hindcast.prepare_iod import MONTH_FREQUENCY
from analysis.drought_hindcast.study_area import OBSERVED_SEASONS_FILE

ALL_REGIONS = "All regions"
NEAR_TERM_SCENARIO = "ML1"
IMPACT_COLUMN = "is_followed_by_impact"
# Negative values are months within the season.
MONTHS_AFTER_SEASON_END = range(-3, 7)
# The current situation is compared over this many months after and before a season.
AFTER_SEASON_MONTH_COUNT = 6
BEFORE_SEASON_MONTH_COUNT = 6


def main() -> None:
    phases = load_region_phases()

    projection_pairs = pd.concat(
        pair_projections_with_later_situations(region_phases).assign(
            region_key=region_key
        )
        for region_key, region_phases in phases.groupby("region_key")
    )
    projection_check = pd.DataFrame(
        [
            {
                "region_key": region_key,
                "scenario": scenario,
                **score_projections(scenario_pairs),
            }
            for region_key, region_pairs in {
                ALL_REGIONS: projection_pairs,
                **dict(tuple(projection_pairs.groupby("region_key"))),
            }.items()
            for scenario, scenario_pairs in region_pairs.groupby("scenario")
            # Lesotho has too few pairs to score.
            if len(scenario_pairs) >= FEWS_NET_MINIMUM_SEASON_COUNT
        ]
    )
    projection_check.to_csv(FEWS_NET_PROJECTION_CHECK_FILE, index=False)
    print(f"Wrote {len(projection_check)} rows to {FEWS_NET_PROJECTION_CHECK_FILE}")
    print(projection_check.to_string(index=False))

    observed = pd.read_csv(OBSERVED_SEASONS_FILE)
    seasons = pd.concat(
        compare_situations_around_seasons(
            phases.loc[phases["region_key"] == region_season.region_key],
            observed.loc[observed["region_season"] == region_season.name],
            region_season,
        )
        for region_season in REGION_SEASONS
    )
    season_counts = seasons.groupby("region_season")["season_year"].count()
    seasons = seasons.loc[
        seasons["region_season"].isin(
            season_counts.index[season_counts >= FEWS_NET_MINIMUM_SEASON_COUNT]
        )
    ]
    seasons.to_csv(
        FEWS_NET_SEASON_OUTCOMES_FILE, index=False, float_format=OUTPUT_FLOAT_FORMAT
    )
    print(f"Wrote {len(seasons)} rows to {FEWS_NET_SEASON_OUTCOMES_FILE}")
    after_season = score_situations_after_seasons(seasons)
    after_season.to_csv(FEWS_NET_AFTER_SEASON_FILE, index=False)
    print(f"Wrote {len(after_season)} rows to {FEWS_NET_AFTER_SEASON_FILE}")
    print(after_season.to_string(index=False))

    monthly_ranks = pd.concat(
        rank_near_term_shares_around_season_end(
            phases.loc[phases["region_key"] == region_season.region_key],
            observed.loc[observed["region_season"] == region_season.name],
            region_season,
        )
        for region_season in REGION_SEASONS
    )
    around_season_end = score_months_around_season_end(monthly_ranks)
    around_season_end.to_csv(FEWS_NET_AROUND_SEASON_END_FILE, index=False)
    print(f"Wrote {len(around_season_end)} rows to {FEWS_NET_AROUND_SEASON_END_FILE}")
    print(
        around_season_end.pivot(
            index="scope", columns="months_after_season_end", values="roc_area"
        ).to_string()
    )


def pair_projections_with_later_situations(region_phases: pd.DataFrame) -> pd.DataFrame:
    """One row per projection and current situation that was classified within its period."""
    is_current_situation = region_phases["scenario"] == CURRENT_SITUATION_SCENARIO
    current_situations = region_phases.loc[is_current_situation]
    rows = []
    for _, projection in region_phases.loc[~is_current_situation].iterrows():
        current_share = find_current_share(
            current_situations, projection[REPORT_MONTH_COLUMN]
        )
        later_months = current_situations[REPORT_MONTH_COLUMN]
        later_situations = current_situations.loc[
            (later_months > projection[REPORT_MONTH_COLUMN])
            & (later_months >= projection[PROJECTION_START_COLUMN])
            & (later_months <= projection[PROJECTION_END_COLUMN])
        ]
        if current_share is None:
            continue
        rows.extend(
            {
                "scenario": projection["scenario"],
                REPORT_MONTH_COLUMN: projection[REPORT_MONTH_COLUMN],
                "projected_share": projection[CRISIS_OR_WORSE_COLUMN],
                "current_share": current_share,
                "later_share": later_share,
            }
            for later_share in later_situations[CRISIS_OR_WORSE_COLUMN]
        )
    return pd.DataFrame(rows)


def score_projections(pairs: pd.DataFrame) -> dict[str, int | float]:
    """How close the projection came to the later situation, next to assuming no change."""
    projected_change = pairs["projected_share"] - pairs["current_share"]
    actual_change = pairs["later_share"] - pairs["current_share"]
    has_projected_change = projected_change != 0
    return {
        "pair_count": len(pairs),
        "mean_absolute_error": _round(
            (pairs["projected_share"] - pairs["later_share"]).abs().mean()
        ),
        "mean_absolute_error_of_no_change": _round(actual_change.abs().mean()),
        "mean_error": _round((pairs["projected_share"] - pairs["later_share"]).mean()),
        "correlation_of_changes": _round(projected_change.corr(actual_change)),
        "projected_change_count": int(has_projected_change.sum()),
        "share_of_changes_in_the_right_direction": _round(
            (
                np.sign(projected_change[has_projected_change])
                == np.sign(actual_change[has_projected_change])
            ).mean()
        ),
    }


def compare_situations_around_seasons(
    region_phases: pd.DataFrame,
    observed_seasons: pd.DataFrame,
    region_season: RegionSeason,
) -> pd.DataFrame:
    """Per observed season, the share in Phase 3 or worse in the current situations of the
    months after it, and its change from the latest current situation before it.

    Both also as a rank among the other seasons, to compare between regions, and
    whether the season counts as an impact season.
    """
    current_situations = region_phases.loc[
        region_phases["scenario"] == CURRENT_SITUATION_SCENARIO
    ]
    months = current_situations[REPORT_MONTH_COLUMN]
    rows = []
    for _, season in observed_seasons.iterrows():
        season_start = pd.Period(
            year=int(season["season_year"]),
            month=region_season.months[0],
            freq=MONTH_FREQUENCY,
        )
        season_end = season_start + len(region_season.months) - 1
        is_after = (months > season_end) & (
            months <= season_end + AFTER_SEASON_MONTH_COUNT
        )
        is_before = (months < season_start) & (
            months >= season_start - BEFORE_SEASON_MONTH_COUNT
        )
        if not is_after.any() or not is_before.any():
            continue
        share_after = current_situations.loc[is_after, CRISIS_OR_WORSE_COLUMN].mean()
        share_before = current_situations.loc[
            months[is_before].idxmax(), CRISIS_OR_WORSE_COLUMN
        ]
        rows.append(
            {
                "region_season": region_season.name,
                "season_year": int(season["season_year"]),
                "is_drought": season[
                    get_observed_drought_column(DEFAULT_DROUGHT_DEFINITION)
                ],
                "share_after": share_after,
                "change": share_after - share_before,
            }
        )
    seasons = pd.DataFrame(rows)
    if seasons.empty:
        return seasons
    seasons["is_drought"] = to_booleans(seasons, "is_drought")
    for column in ("share_after", "change"):
        seasons[f"{column}_rank"] = calculate_rank_among_others(
            seasons[column].to_numpy()
        )
    # An impact season: a rise that is in the upper third of the rises of the region-season.
    seasons[IMPACT_COLUMN] = (seasons["change"] > 0) & (
        seasons["change_rank"] >= UPPER_TERCILE
    )
    return seasons


def score_situations_after_seasons(seasons: pd.DataFrame) -> pd.DataFrame:
    """Whether drought seasons are followed by more area in Phase 3 or worse than other seasons."""
    pooled_names = [
        region_season.name
        for region_season in REGION_SEASONS
        if region_season.is_in_pooled_results
    ]
    seasons_by_scope = {
        POOLED_FEWS_NET_REGION_SEASONS: seasons.loc[
            seasons["region_season"].isin(pooled_names)
        ],
        **dict(tuple(seasons.groupby("region_season", sort=False))),
    }
    rows = []
    for scope, scope_seasons in seasons_by_scope.items():
        is_drought = scope_seasons["is_drought"].to_numpy()
        is_one_region_season = scope != POOLED_FEWS_NET_REGION_SEASONS
        row: dict[str, str | int | float | None] = {
            "scope": scope,
            "season_count": len(scope_seasons),
            "drought_count": int(is_drought.sum()),
        }
        for column in ("share_after", "change"):
            row[f"mean_{column}_of_droughts"] = _round(
                scope_seasons.loc[is_drought, column].mean()
            )
            row[f"mean_{column}_of_other_seasons"] = _round(
                scope_seasons.loc[~is_drought, column].mean()
            )
            discrimination = measure_discrimination(
                scope_seasons[f"{column}_rank"].to_numpy(),
                is_drought,
                is_one_region_season,
            )
            row[f"roc_area_of_{column}"] = discrimination["roc_area"]
            row[f"roc_area_of_{column}_probability_by_chance"] = discrimination[
                "roc_area_probability_by_chance"
            ]
        rows.append(row)
    return pd.DataFrame(rows)


def rank_near_term_shares_around_season_end(
    region_phases: pd.DataFrame,
    observed_seasons: pd.DataFrame,
    region_season: RegionSeason,
) -> pd.DataFrame:
    """Per observed season and month around its end, the share in Phase 3 or worse in the
    near-term projection of the latest report up to that month: as a rank among the
    other seasons, and against the mean of all seasons.
    """
    near_term = region_phases.loc[region_phases["scenario"] == NEAR_TERM_SCENARIO]
    report_months = near_term[REPORT_MONTH_COLUMN]
    rows = []
    for months_after_season_end in MONTHS_AFTER_SEASON_END:
        month_rows = []
        for _, season in observed_seasons.iterrows():
            month = (
                pd.Period(
                    year=int(season["season_year"]),
                    month=region_season.months[0],
                    freq=MONTH_FREQUENCY,
                )
                + len(region_season.months)
                - 1
                + months_after_season_end
            )
            is_usable = (report_months <= month) & (
                report_months >= month - FEWS_NET_MAXIMUM_CURRENT_SITUATION_AGE_MONTHS
            )
            if not is_usable.any():
                continue
            month_rows.append(
                {
                    "region_season": region_season.name,
                    "season_year": int(season["season_year"]),
                    "months_after_season_end": months_after_season_end,
                    "is_drought": season[
                        get_observed_drought_column(DEFAULT_DROUGHT_DEFINITION)
                    ],
                    "share": near_term.loc[
                        report_months[is_usable].idxmax(), CRISIS_OR_WORSE_COLUMN
                    ],
                }
            )
        month_seasons = pd.DataFrame(month_rows)
        if len(month_seasons) < FEWS_NET_MINIMUM_SEASON_COUNT:
            continue
        month_seasons["is_drought"] = to_booleans(month_seasons, "is_drought")
        month_seasons["share_rank"] = calculate_rank_among_others(
            month_seasons["share"].to_numpy()
        )
        # Against the usual share of the region in that month, to compare between regions.
        month_seasons["share_anomaly"] = (
            month_seasons["share"] - month_seasons["share"].mean()
        )
        rows.append(month_seasons)
    return pd.concat(rows) if rows else pd.DataFrame()


def score_months_around_season_end(monthly_ranks: pd.DataFrame) -> pd.DataFrame:
    """Per month around the season end, the near-term share of drought seasons and of
    other seasons against the usual share, and its ROC area."""
    pooled_names = [
        region_season.name
        for region_season in REGION_SEASONS
        if region_season.is_in_pooled_results
    ]
    ranks_by_scope = {
        POOLED_FEWS_NET_REGION_SEASONS: monthly_ranks.loc[
            monthly_ranks["region_season"].isin(pooled_names)
        ],
        **dict(tuple(monthly_ranks.groupby("region_season", sort=False))),
    }
    return pd.DataFrame(
        [
            {
                "scope": scope,
                "months_after_season_end": months_after_season_end,
                "season_count": len(month_ranks),
                "drought_count": int(month_ranks["is_drought"].sum()),
                "mean_share_anomaly_of_droughts": _round(
                    month_ranks.loc[month_ranks["is_drought"], "share_anomaly"].mean()
                ),
                "mean_share_anomaly_of_other_seasons": _round(
                    month_ranks.loc[~month_ranks["is_drought"], "share_anomaly"].mean()
                ),
                **measure_discrimination(
                    month_ranks["share_rank"].to_numpy(),
                    month_ranks["is_drought"].to_numpy(),
                    is_one_region_season=scope != POOLED_FEWS_NET_REGION_SEASONS,
                ),
            }
            for scope, scope_ranks in ranks_by_scope.items()
            for months_after_season_end, month_ranks in scope_ranks.groupby(
                "months_after_season_end"
            )
        ]
    )


def _round(value: float) -> float:
    return round(float(value), SCORE_DECIMALS)


if __name__ == "__main__":
    main()
