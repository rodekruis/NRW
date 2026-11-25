from pipelines.flood.footprint_method import RegriddingMethod

MINIMUM_RETURN_PERIOD_YEARS = 1.5
MINIMUM_RETURN_PERIOD = f"{MINIMUM_RETURN_PERIOD_YEARS:g}yr"

# Flood depth greyscale 1..255 maps linearly to 0..this depth; must match the API's flood depth colorization config.
FLOOD_DEPTH_GREYSCALE_MAX_METRES = 10.0

# Minimum allowed number of 'ensemble' forecast files in the GloFAS data.
# If fewer than this, fail the data load (which alerts the team of an error)
# and do not run the forecast pipeline.
GLOFAS_MIN_ENSEMBLE_COUNT = 34  # 2/3 of the total number of ensemble members

# Percentile bounds for the waterDischarge geo-feature attribute's low/high forecast range.
WATER_DISCHARGE_LOW_PERCENTILE = 10
WATER_DISCHARGE_HIGH_PERCENTILE = 90

# --- Flood footprint: a return period per GloFAS cell ---

# Version of the return period curves. ECMWF has not published the v5 curves yet.
GLOFAS_VERSION = "v4"

# Smaller cells do not drive the footprint; their pixels take the nearest cell that does. The
# flood maps cover rivers from 500 km2 (Dottori et al. 2022, https://doi.org/10.5194/essd-14-1549-2022).
MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES = 500.0
# Cells with a flatter curve do not drive either: on such a curve, even no water reads as a flood.
# GloFAS uses the same value on the forecast discharge: it only shows a flood signal where the
# discharge exceeds 0.1 m3/s (https://confluence.ecmwf.int/display/CEMS/GloFAS+Flood+Summary).
MINIMUM_GUMBEL_SCALE_CUBIC_METRES_PER_SECOND = 0.1

REGRIDDING_METHOD = RegriddingMethod.NEAREST

# Shallower water is left out of the footprint and of the exposed population.
MINIMUM_FLOOD_DEPTH_METRES = 0.2
