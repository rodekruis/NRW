"""Weight of each grid cell in a region average."""

import numpy as np
from analysis.drought_hindcast.study_area import Bounds
from rasterio.features import geometry_mask
from rasterio.transform import from_origin


def calculate_cell_weights(
    geometry: dict, bounds: Bounds, cell_size_degrees: float, subcell_count: int
) -> np.ndarray:
    """Weight per grid cell, rows running north to south.

    The weight is the share of the cell inside the region times the cosine of its
    latitude, which is proportional to its area. The share is the fraction of the cell's
    subcell_count x subcell_count subcell centres that fall inside the region.
    """
    row_count = round((bounds.north - bounds.south) / cell_size_degrees)
    column_count = round((bounds.east - bounds.west) / cell_size_degrees)
    subcell_size_degrees = cell_size_degrees / subcell_count
    is_inside = geometry_mask(
        [geometry],
        out_shape=(row_count * subcell_count, column_count * subcell_count),
        transform=from_origin(
            bounds.west, bounds.north, subcell_size_degrees, subcell_size_degrees
        ),
        invert=True,
    )
    share_inside = is_inside.reshape(
        row_count, subcell_count, column_count, subcell_count
    ).mean(axis=(1, 3))
    latitudes = bounds.north - (np.arange(row_count) + 0.5) * cell_size_degrees
    return share_inside * np.cos(np.deg2rad(latitudes))[:, np.newaxis]
