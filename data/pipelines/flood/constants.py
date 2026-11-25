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

# Cells below this do not drive the footprint: the flood maps hold few floods of rivers that
# small, so the flooding around such a cell mostly belongs to a larger river. Their pixels take
# the return period of the nearest cell that does. The method behind the flood maps uses rivers
# from 500 km2 (Dottori et al. 2022, https://doi.org/10.5194/essd-14-1549-2022, for the European
# maps). Not agreed (AB#42674); see analysis/flood_footprint/check_sensitivity.py.
MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES = 500.0
# Cells with a flatter curve do not drive the footprint either: on such a curve, no water at all
# reads as a flood. Provisional (AB#42674): in the one forecast checked, 0.1 switches off only
# cells without water, while 1.0 also switches off cells with real flow. See
# analysis/flood_footprint/check_sensitivity.py.
MINIMUM_GUMBEL_SCALE_CUBIC_METRES_PER_SECOND = 0.1

REGRIDDING_METHOD = RegriddingMethod.NEAREST

# Shallower water is left out of the footprint and of the exposed population. Proposed, not agreed.
MINIMUM_FLOOD_DEPTH_METRES = 0.2
