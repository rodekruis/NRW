from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import Affine

_LOCATION_BAND = "location"
_SCALE_BAND = "scale"
_UPSTREAM_AREA_BAND = "upstream_area"
_BAND_NAMES = (_LOCATION_BAND, _SCALE_BAND, _UPSTREAM_AREA_BAND)

# How far, in cells, two grids may be apart and still count as the same lattice.
_GRID_ALIGNMENT_TOLERANCE_CELLS = 0.01


def get_glofas_return_period_curves_filename(country: str, glofas_version: str) -> str:
    return f"{country}_glofas_{glofas_version}_return_period_curves.tif"


@dataclass
class GlofasReturnPeriodCurves:
    """
    Per GloFAS cell: the Gumbel curve of annual peak discharge (location and scale, m3/s) and the
    upstream area (m2). Cells without a curve are NaN.
    """

    location: np.ndarray
    scale: np.ndarray
    upstream_area: np.ndarray
    transform: Affine
    crs: str

    @staticmethod
    def from_geotiff(content: bytes) -> GlofasReturnPeriodCurves:
        with MemoryFile(content) as memory_file, memory_file.open() as dataset:
            band_index_by_name = {
                name: index + 1 for index, name in enumerate(dataset.descriptions)
            }
            missing_bands = [
                name for name in _BAND_NAMES if name not in band_index_by_name
            ]
            if missing_bands:
                raise ValueError(
                    f"Return period curves miss bands {missing_bands}; found {dataset.descriptions}"
                )
            location, scale, upstream_area = (
                dataset.read(band_index_by_name[name], masked=True)
                .astype(np.float64)
                .filled(np.nan)
                for name in _BAND_NAMES
            )
            return GlofasReturnPeriodCurves(
                location=location,
                scale=scale,
                upstream_area=upstream_area,
                transform=dataset.transform,
                crs=str(dataset.crs),
            )

    def write_geotiff(self, path: Path) -> None:
        bands = (self.location, self.scale, self.upstream_area)
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=self.location.shape[0],
            width=self.location.shape[1],
            count=len(bands),
            dtype=rasterio.float64,
            crs=self.crs,
            transform=self.transform,
            nodata=np.nan,
            compress="deflate",
        ) as dataset:
            for index, (name, band) in enumerate(
                zip(_BAND_NAMES, bands, strict=True), start=1
            ):
                dataset.write(band.astype(np.float64), index)
                dataset.set_band_description(index, name)

    def aligned_to(
        self, transform: Affine, shape: tuple[int, int]
    ) -> GlofasReturnPeriodCurves:
        """
        The curves on another grid of the same lattice, such as a forecast's country slice.
        Cells of that grid outside this one are NaN. Raises ValueError when the cells of the two
        grids do not line up: sampling the curve of a neighbouring cell gives wrong return periods.
        """
        row_offset = (transform.f - self.transform.f) / self.transform.e
        column_offset = (transform.c - self.transform.c) / self.transform.a
        row_count, column_count = shape
        cell_size_drift = max(
            abs(transform.e / self.transform.e - 1) * row_count,
            abs(transform.a / self.transform.a - 1) * column_count,
        )
        lattice_offset = max(
            abs(row_offset - round(row_offset)),
            abs(column_offset - round(column_offset)),
        )
        if max(cell_size_drift, lattice_offset) > _GRID_ALIGNMENT_TOLERANCE_CELLS:
            raise ValueError(
                "Grid does not line up with the GloFAS return period curves: "
                f"curves {_describe_grid(self.transform)}, grid {_describe_grid(transform)}"
            )

        first_row, first_column = round(row_offset), round(column_offset)
        own_row_count, own_column_count = self.location.shape
        rows = np.arange(row_count) + first_row
        columns = np.arange(column_count) + first_column
        inside = np.ix_(
            (rows >= 0) & (rows < own_row_count),
            (columns >= 0) & (columns < own_column_count),
        )
        own_window = np.ix_(
            rows[(rows >= 0) & (rows < own_row_count)],
            columns[(columns >= 0) & (columns < own_column_count)],
        )

        def align(band: np.ndarray) -> np.ndarray:
            aligned = np.full(shape, np.nan, dtype=np.float64)
            aligned[inside] = band[own_window]
            return aligned

        return GlofasReturnPeriodCurves(
            location=align(self.location),
            scale=align(self.scale),
            upstream_area=align(self.upstream_area),
            transform=transform,
            crs=self.crs,
        )


def _describe_grid(transform: Affine) -> str:
    return f"from ({transform.c:g}, {transform.f:g}) in cells of {transform.a:g} x {-transform.e:g} degrees"
