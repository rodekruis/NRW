"""Scores shared by the indicators that are set next to SEAS5."""

import numpy as np
from analysis.drought_hindcast.calculate_skill import (
    calculate_probability_by_chance,
    calculate_scores,
    CHANCE_PROBABILITY_DECIMALS,
    SCORE_DECIMALS,
)
from analysis.drought_hindcast.compare_with_skill_review import calculate_roc_area

Scores = dict[str, int | float | None]


def score_alert(
    is_alert: np.ndarray,
    is_drought: np.ndarray,
    season_years: np.ndarray,
    is_one_region_season: bool,
    random_generator: np.random.Generator,
) -> Scores:
    """Hit rate and false-alarm ratio with their ranges, and the probability of the hits
    by chance. That probability treats the seasons as independent, so it is left out for
    pooled region-seasons.
    """
    scores = calculate_scores(
        is_alert=is_alert,
        is_drought=is_drought,
        season_years=season_years,
        random_generator=random_generator,
    )
    return {
        **scores,
        "probability_by_chance": (
            round(
                calculate_probability_by_chance(
                    hit_count=int(scores["hit_count"]),
                    alert_count=int(scores["alert_count"]),
                    drought_count=int(scores["drought_count"]),
                    season_count=int(scores["season_count"]),
                ),
                CHANCE_PROBABILITY_DECIMALS,
            )
            if is_one_region_season
            else None
        ),
    }


def measure_discrimination(
    values_towards_drought: np.ndarray,
    is_drought: np.ndarray,
    is_one_region_season: bool,
) -> Scores:
    """ROC area of a value that is higher when a drought is more likely, and its probability
    by chance. That probability is left out for pooled region-seasons.
    """
    roc_area, probability_by_chance = calculate_roc_area(
        values_towards_drought, is_drought
    )
    return {
        "roc_area": round(roc_area, SCORE_DECIMALS),
        "roc_area_probability_by_chance": (
            round(probability_by_chance, CHANCE_PROBABILITY_DECIMALS)
            if is_one_region_season
            else None
        ),
    }
