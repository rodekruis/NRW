"""
Helper functions relating to image processing
"""

import io

import numpy as np
from PIL import Image
from rasterio.io import MemoryFile

# Allow PIL to open large images
Image.MAX_IMAGE_PIXELS = None  # noqa: V101


def geotiff_to_rgba_data_array(tif_data: bytes):
    """
    Converts a GeoTIFF to an RGBA int array, without changing the projection, and
    also returns metadata from the original GeoTIFF.
    This is used to convert GeoTIFFs to PNG with three decimal precision.

    Population values are encoded across the R, G, B, A channels,
    allowing for a per pixel range of 256^4 (over 4 million per pixel, with 3 decimal precision).
    Even with very dense countries, we wouldn't see more than 15k per pixel.
    RGB encoding gives us 16.8k per pixel. Since this risks being too low for some areas,
    RGBA encoding was used. This only adds a small increase in file size (about 10%).

    The value can be decoded with: value = (R * 16777216 + G * 65536 + B * 256 + A) / 1000

    Note: This conversion also does this to the data (due to PNG limitations):
      - NoData values are set to 0
      - Values are clamped between 0 and about 4.29 million (max encoding value)
      - All decimal values are rounded to 3 decimal precision.
    """
    with MemoryFile(tif_data) as memfile, memfile.open() as src:
        if src.count != 1:
            raise ValueError(
                f"Expected a single-band GeoTIFF, but got {src.count} bands."
            )

        raw_data = src.read(1)

        geo_data = {
            "width": src.width,
            "height": src.height,
            "count": 4,  # this will be 4 since this converts to RGBA
            "crs": str(src.crs),
            "transform": list(src.transform),
            "bounds": {
                "left": src.bounds.left,
                "bottom": src.bounds.bottom,
                "right": src.bounds.right,
                "top": src.bounds.top,
            },
            "res": src.res,
            "scales": src.scales,
            "offsets": src.offsets,
            "nodata": 0,  # NoData values are set to 0 with the conversion
            "dtype": "uint32",  # The data type of the output array (after conversion)
        }

        # Replace nodata with 0
        if src.nodata is not None:
            if np.isnan(src.nodata):
                raw_data = np.where(np.isnan(raw_data), 0, raw_data)
            else:
                raw_data = np.where(raw_data == src.nodata, 0, raw_data)

        # This does 3 things:
        # - Remove negatives (Clip negatives to 0)
        # - Preserve 3 decimal precision before int conversion (by multiplying by 1000)
        # - Round to integer (PNG needs integers)
        values = np.round(np.clip(raw_data, 0, None) * 1000).astype(np.uint64)

        # Get max value and throw if any values go beyond the encoding max
        max_value = int(values.max())
        uint32_max = 256**4 - 1
        if max_value > uint32_max:
            # This would never be hit for population data (unless there is a data error),
            # but this may be hit in non-population data.
            # Throw an error, rather than clipping the data.
            raise ValueError(
                f"Max value {max_value} exceeds RGBA encoding capacity ({uint32_max})."
            )

        # Update the max value in the meta data
        geo_data["max_value"] = max_value

        # Encode value into R, G, B, A channels
        # This works by shifting bits by 3, 2, 1, or 0 bytes,
        # and then grabbing the last byte.
        # It's like taking a number in hex (such as EF9A2F1C) and
        # splitting it into its 4 components (i.e. EF 9A 2F 1C).
        r = ((values >> 24) & 0xFF).astype(np.uint8)
        g = ((values >> 16) & 0xFF).astype(np.uint8)
        b = ((values >> 8) & 0xFF).astype(np.uint8)
        a = (values & 0xFF).astype(np.uint8)

        # Place into an RGBA array
        rgba_array = np.dstack([r, g, b, a])
        return geo_data, rgba_array


# Number of image rows decoded per chunk in rgba_png_to_float_array.
# Decoding a full raster at once needs several full-image-sized temporary
# arrays for the bit-shift/OR math (10+ GB for a full-resolution country
# population raster, ~230-250 million pixels) and reliably OOMs pipeline
# hosts. Row-chunking bounds peak memory to roughly one chunk's worth of
# temporaries, independent of overall image size.
_RGBA_DECODE_CHUNK_ROWS = 1024


def rgba_png_to_float_array(png_in_bytes: bytes) -> np.ndarray:
    """
    Inverse of geotiff_to_rgba_data_array's RGBA encoding.
    Opens a PNG whose pixel values encode an integer across the R, G, B, A channels.
    The formula is:
    (R * 16777216 + G * 65536 + B * 256 + A)/1000
    The function returns a 2D array of floats.

    Decoding is done in row chunks rather than on the whole image at once, to
    bound peak memory for full-resolution rasters (see _RGBA_DECODE_CHUNK_ROWS).
    """
    img = Image.open(io.BytesIO(png_in_bytes)).convert("RGBA")
    rgba = np.array(img, dtype=np.uint8)

    height, width, _ = rgba.shape
    values = np.empty((height, width), dtype=np.float64)

    for start_row in range(0, height, _RGBA_DECODE_CHUNK_ROWS):
        end_row = min(start_row + _RGBA_DECODE_CHUNK_ROWS, height)
        chunk = rgba[start_row:end_row].astype(np.uint32)

        r = chunk[:, :, 0]
        g = chunk[:, :, 1]
        b = chunk[:, :, 2]
        a = chunk[:, :, 3]

        decoded = (r << 24) | (g << 16) | (b << 8) | a
        values[start_row:end_row] = np.round(decoded.astype(np.float64) / 1000, 3)

    return values
