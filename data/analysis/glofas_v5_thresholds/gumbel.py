"""The Gumbel fit and thresholds of ECMWF's lisflood-utilities, shared by the comparison and the station locations."""

import numpy as np


def fit_gumbel(annual_maxima: np.ndarray) -> tuple[float, float]:
    """Location and scale from the first two sample L-moments, as in ECMWF's lisflood-utilities."""
    sorted_maxima = np.sort(annual_maxima)
    count = len(sorted_maxima)
    first_probability_weighted_moment = (
        np.sum(np.arange(count) / (count - 1) * sorted_maxima) / count
    )
    first_l_moment = float(np.mean(sorted_maxima))
    second_l_moment = 2 * first_probability_weighted_moment - first_l_moment
    scale = second_l_moment / np.log(2)
    location = first_l_moment - np.euler_gamma * scale
    return location, scale


def gumbel_threshold(return_period: float, location: float, scale: float) -> float:
    return location - scale * np.log(np.log(return_period / (return_period - 1)))
