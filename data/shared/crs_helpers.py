"""
Helper functions for the coordinate reference system (CRS) of geodata.

All geodata in the pipelines and in the seed data is in DEFAULT_CRS. Geodata in a
different CRS is rejected where it enters, it is not reprojected.
See docs/coordinate-reference-system.md.
"""

from pipelines.constants import DEFAULT_CRS

MAX_LONGITUDE = 180
MAX_LATITUDE = 90


def validate_crs(crs: object, source: str) -> None:
    """
    Raise when the CRS that the source gives for its geodata is not DEFAULT_CRS.
    The CRS can be a string or a CRS object of rasterio or fiona, or None when the
    source gives no CRS.
    """
    if crs != DEFAULT_CRS:
        raise ValueError(
            f"{source} has CRS '{crs}', but only {DEFAULT_CRS} is supported"
        )


def is_in_longitude_latitude_range(bounds: tuple[float, float, float, float]) -> bool:
    """
    Tell if the bounds (min_x, min_y, max_x, max_y) are longitudes and latitudes in degrees.
    Use this where geodata gives no CRS, or to find a CRS that is not correct:
    coordinates in a projected CRS (metres) are almost always outside this range.
    """
    min_x, min_y, max_x, max_y = bounds
    return (
        abs(min_x) <= MAX_LONGITUDE
        and abs(max_x) <= MAX_LONGITUDE
        and abs(min_y) <= MAX_LATITUDE
        and abs(max_y) <= MAX_LATITUDE
    )
