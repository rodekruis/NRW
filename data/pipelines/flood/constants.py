MINIMUM_RETURN_PERIOD_YEARS = 1.5
MINIMUM_RETURN_PERIOD = f"{MINIMUM_RETURN_PERIOD_YEARS:g}yr"

# Version of the return period curves. ECMWF has not published the v5 curves yet.
GLOFAS_VERSION = "v4"

# Flood depth greyscale 1..255 maps linearly to 0..this depth; must match the API's flood depth colorization config.
FLOOD_DEPTH_GREYSCALE_MAX_METRES = 10.0

# Minimum allowed number of 'ensemble' forecast files in the GloFAS data.
# If fewer than this, fail the data load (which alerts the team of an error)
# and do not run the forecast pipeline.
GLOFAS_MIN_ENSEMBLE_COUNT = 34  # 2/3 of the total number of ensemble members

# Percentile bounds for the waterDischarge geo-feature attribute's low/high forecast range.
WATER_DISCHARGE_LOW_PERCENTILE = 10
WATER_DISCHARGE_HIGH_PERCENTILE = 90
