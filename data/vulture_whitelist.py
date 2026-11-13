# Vulture whitelist. We "use" names here so vulture does not flag them as dead code.
# Regenerate candidates with: uv run vulture --make-whitelist
# Prefer removing dead code over adding entries here.

# --- Intentional: used dynamically, serialized by name, mirrored from backend, or kept for iteration ---
POPULATION  # GeoJSON property (data_management/seed_data_management/admin_areas/admin_area_geojson.py)
low  # WaterDischargeTimeSeriesEntry, mirrors exposure-geo-feature.dto.ts (pipelines/infra/data_types/dtos.py)
high  # WaterDischargeTimeSeriesEntry, mirrors exposure-geo-feature.dto.ts (pipelines/infra/data_types/dtos.py)
overlap_of_old_footprint  # Serialized in the station migration report via dataclasses.asdict
SCHEDULED  # RunOrigin value supplied by the deployed scheduler through the environment
DESTIN_E  # Generated from the API enum contract; retained for shared enum parity
COMPOUND_FLOODS  # Generated from the API enum contract; retained for shared enum parity
RED_CROSS_BRANCHES  # Generated from the API enum contract; retained for shared enum parity
CLINICS  # Generated from the API enum contract; retained for shared enum parity
calculate_forecasts  # Hazard forecast template copied when adding a new hazard
GEFS_ENSEMBLE_COUNT  # Preliminary tropical cyclone pipeline reference (pipelines/tropical_cyclone/constants.py)
GEFS_WIND_MEMBER_IDS  # Preliminary tropical cyclone pipeline reference (pipelines/tropical_cyclone/constants.py)
GEFS_TRACK_MEMBER_IDS  # Preliminary tropical cyclone pipeline reference (pipelines/tropical_cyclone/constants.py)
ECMWF_PERTURBED_MEMBER_NUMBERS  # Preliminary tropical cyclone pipeline reference (pipelines/tropical_cyclone/constants.py)
ECMWF_TRACK_CONTROL_MEMBER_NUMBER  # Preliminary tropical cyclone pipeline reference (pipelines/tropical_cyclone/constants.py)
ECMWF_ENSEMBLE_COUNT  # Preliminary tropical cyclone pipeline reference (pipelines/tropical_cyclone/constants.py)
ECMWF_TRACK_FIX_INTERVAL_HOURS  # Preliminary tropical cyclone pipeline reference (pipelines/tropical_cyclone/constants.py)
_load_ecmwf_track_fixes  # Starting point for ECMWF multi-storm support (pipelines/tropical_cyclone/extract_track.py)
