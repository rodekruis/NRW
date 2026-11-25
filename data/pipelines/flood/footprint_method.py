"""
Flood footprint from a return period per GloFAS cell, in three steps:

1. discharge to return period, on each cell's own Gumbel curve of annual peak discharge;
2. return period from the GloFAS grid onto the flood map grid;
3. return period to depth, interpolated between the flood maps.

Our own implementation of CLIMADA's GloFAS river flood module (rp_comp, regrid and flood_depth in
climada_petals.hazard.rf_glofas.transform_ops), on plain arrays and grids.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from enum import StrEnum
from itertools import pairwise

import numpy as np
from rasterio.transform import Affine
from scipy.spatial import KDTree

# The flood maps are interpolated towards zero depth at this return period.
ZERO_DEPTH_RETURN_PERIOD = 1.0

# Bounds the memory of the temporary arrays that regridding needs per flood map pixel.
_REGRIDDING_CHUNK_ROWS = 512


class RegriddingMethod(StrEnum):
    # Each pixel takes the return period of the nearest cell that drives the footprint.
    NEAREST = "nearest"
    # Each pixel blends the four cells around it. Cells that do not drive the footprint first
    # take the return period of the nearest cell that does.
    BILINEAR = "bilinear"


def compute_return_period(
    discharge: np.ndarray,
    location: np.ndarray,
    scale: np.ndarray,
    maximum_return_period: float,
) -> np.ndarray:
    """
    Return period in years of a discharge on a Gumbel curve of annual peak discharge:
    1 / (1 - exp(-exp(-(discharge - location) / scale))).

    A discharge far below the curve gives 1 year, one far above it the maximum return period.
    Missing inputs give NaN.
    """
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        reduced_variate = (discharge - location) / scale
        # expm1 keeps precision where the exceedance probability is close to zero.
        exceedance_probability = -np.expm1(-np.exp(-reduced_variate))
        return_period = 1.0 / exceedance_probability
    return np.minimum(return_period, maximum_return_period)


def regrid_return_period(
    return_period: np.ndarray,
    source_transform: Affine,
    target_transform: Affine,
    target_shape: tuple[int, int],
    method: RegriddingMethod,
    target_mask: np.ndarray | None = None,
) -> np.ndarray:
    """
    Bring return periods from the GloFAS grid onto the flood map grid.

    Only cells with a finite return period drive the result. Pixels outside target_mask, and all
    pixels when no cell drives, are NaN. Distances are in degrees, so slightly anisotropic away
    from the equator.
    """
    _require_north_up(source_transform)
    _require_north_up(target_transform)

    regridded = np.full(target_shape, np.nan, dtype=np.float32)
    drives = np.isfinite(return_period)
    if not drives.any():
        return regridded

    pixel_x, pixel_y = _cell_centres(target_transform, target_shape)
    sample = (
        _nearest_sampler(return_period, drives, source_transform)
        if method == RegriddingMethod.NEAREST
        else _bilinear_sampler(return_period, drives, source_transform)
    )

    for start_row in range(0, target_shape[0], _REGRIDDING_CHUNK_ROWS):
        rows = slice(start_row, start_row + _REGRIDDING_CHUNK_ROWS)
        chunk_mask = (
            np.ones((len(pixel_y[rows]), target_shape[1]), dtype=bool)
            if target_mask is None
            else target_mask[rows]
        )
        if chunk_mask.any():
            regridded[rows][chunk_mask] = sample(pixel_x, pixel_y[rows], chunk_mask)

    return regridded


def interpolate_flood_depth(
    return_period: np.ndarray,
    load_flood_map: Callable[[int], np.ndarray],
    available_return_periods: Sequence[int],
    minimum_return_period: float,
) -> np.ndarray:
    """
    Flood depth per pixel, interpolated linearly in return period between the flood maps.

    Depth is zero at ZERO_DEPTH_RETURN_PERIOD, so below the lowest map it is a linear scaling of
    that map. Pixels below minimum_return_period, or without a return period, stay dry. Return
    periods above the highest map get the depth of the highest map.

    load_flood_map returns the depth of one flood map on the grid of return_period, with zero
    where it is dry. It is only called for the maps that some pixel lies between.
    """
    map_return_periods = sorted(available_return_periods)
    if not map_return_periods or map_return_periods[0] <= ZERO_DEPTH_RETURN_PERIOD:
        raise ValueError(
            f"Flood maps must have return periods above {ZERO_DEPTH_RETURN_PERIOD:g} year, "
            f"got {map_return_periods}"
        )

    depth = np.zeros(return_period.shape, dtype=np.float32)
    is_wet = np.isfinite(return_period) & (return_period >= minimum_return_period)
    if not is_wet.any():
        return depth

    highest_return_period = map_return_periods[-1]
    capped_return_period = np.minimum(return_period, highest_return_period)

    for lower, upper in pairwise([ZERO_DEPTH_RETURN_PERIOD, *map_return_periods]):
        in_interval = is_wet & (capped_return_period >= lower)
        in_interval &= (
            capped_return_period <= upper
            if upper == highest_return_period
            else capped_return_period < upper
        )
        if not in_interval.any():
            continue

        upper_depth = load_flood_map(int(upper))[in_interval]
        lower_depth = (
            np.zeros_like(upper_depth)
            if lower == ZERO_DEPTH_RETURN_PERIOD
            else load_flood_map(int(lower))[in_interval]
        )
        weight = (capped_return_period[in_interval] - lower) / (upper - lower)
        depth[in_interval] = lower_depth + weight * (upper_depth - lower_depth)

    return np.maximum(depth, 0.0)


_Sampler = Callable[[np.ndarray, np.ndarray, np.ndarray], np.ndarray]


def _nearest_sampler(
    return_period: np.ndarray, drives: np.ndarray, source_transform: Affine
) -> _Sampler:
    cell_x, cell_y = _cell_centres(source_transform, return_period.shape)
    driving_rows, driving_columns = np.nonzero(drives)
    tree = KDTree(np.column_stack([cell_x[driving_columns], cell_y[driving_rows]]))
    driving_return_periods = return_period[driving_rows, driving_columns]

    def sample(
        pixel_x: np.ndarray, pixel_y: np.ndarray, mask: np.ndarray
    ) -> np.ndarray:
        rows, columns = np.nonzero(mask)
        _, nearest = tree.query(np.column_stack([pixel_x[columns], pixel_y[rows]]))
        return driving_return_periods[nearest]

    return sample


def _bilinear_sampler(
    return_period: np.ndarray, drives: np.ndarray, source_transform: Affine
) -> _Sampler:
    cell_x, cell_y = _cell_centres(source_transform, return_period.shape)
    sample_nearest = _nearest_sampler(return_period, drives, source_transform)
    row_count, column_count = return_period.shape
    filled = sample_nearest(
        cell_x, cell_y, np.ones(return_period.shape, dtype=bool)
    ).reshape(return_period.shape)

    def sample(
        pixel_x: np.ndarray, pixel_y: np.ndarray, mask: np.ndarray
    ) -> np.ndarray:
        # Fractional index of each pixel centre between the cell centres; the edge cells extend outwards.
        row_position = np.clip(
            (pixel_y - source_transform.f) / source_transform.e - 0.5, 0, row_count - 1
        )
        column_position = np.clip(
            (pixel_x - source_transform.c) / source_transform.a - 0.5,
            0,
            column_count - 1,
        )
        upper_row = np.floor(row_position).astype(int)
        left_column = np.floor(column_position).astype(int)
        lower_row = np.minimum(upper_row + 1, row_count - 1)
        right_column = np.minimum(left_column + 1, column_count - 1)
        row_weight = (row_position - upper_row)[:, np.newaxis]
        column_weight = column_position - left_column

        upper = (
            filled[np.ix_(upper_row, left_column)] * (1 - column_weight)
            + filled[np.ix_(upper_row, right_column)] * column_weight
        )
        lower = (
            filled[np.ix_(lower_row, left_column)] * (1 - column_weight)
            + filled[np.ix_(lower_row, right_column)] * column_weight
        )
        return (upper * (1 - row_weight) + lower * row_weight)[mask]

    return sample


def _cell_centres(
    transform: Affine, shape: tuple[int, int]
) -> tuple[np.ndarray, np.ndarray]:
    row_count, column_count = shape
    centre_x = transform.c + (np.arange(column_count) + 0.5) * transform.a
    centre_y = transform.f + (np.arange(row_count) + 0.5) * transform.e
    return centre_x, centre_y


def _require_north_up(transform: Affine) -> None:
    if transform.b != 0 or transform.d != 0 or transform.a <= 0 or transform.e >= 0:
        raise ValueError(f"Expected a north-up grid without rotation, got {transform}")
