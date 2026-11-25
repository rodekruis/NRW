MINIMUM_RETURN_PERIOD = "1.5yr"

# Flood depth greyscale 1..255 maps linearly to 0..this depth; must match the API's flood depth colorization config.
FLOOD_DEPTH_GREYSCALE_MAX_METRES = 10.0

# Minimum allowed number of 'ensemble' forecast files in the GloFAS data.
# If fewer than this, fail the data load (which alerts the team of an error)
# and do not run the forecast pipeline.
GLOFAS_MIN_ENSEMBLE_COUNT = 34  # 2/3 of the total number of ensemble members

# An admin area belongs to a station's spatial extent geometry when at least this share of the
# admin area lies inside it. It drops the slivers along the edge; on the current stations it still
# keeps admin areas covering 98.8% or more of each spatial extent.
MINIMUM_ADMIN_AREA_SHARE_IN_SPATIAL_EXTENT = 0.01

# Percentile bounds for the waterDischarge geo-feature attribute's low/high forecast range.
WATER_DISCHARGE_LOW_PERCENTILE = 10
WATER_DISCHARGE_HIGH_PERCENTILE = 90
