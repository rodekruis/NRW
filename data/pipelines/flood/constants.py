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

# --- Flood footprint: a return period per GloFAS cell (AB#42674) ---

# GloFAS version of the return period curves (Gumbel parameters and upstream area per cell).
# v5 is pre-operational; ECMWF has not published its curves yet.
GLOFAS_VERSION = "v4"

# Cells below these do not drive the footprint: a small forecast change moves them several
# return periods. Their pixels take the return period of the nearest cell that does.
MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES = 500.0
MINIMUM_GUMBEL_SCALE_CUBIC_METRES_PER_SECOND = 1.0

REGRIDDING_METHOD = RegriddingMethod.NEAREST

# Shallower water is left out of the footprint and of the exposed population. Proposed, not agreed.
MINIMUM_FLOOD_DEPTH_METRES = 0.2
