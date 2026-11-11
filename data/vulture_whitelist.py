# Vulture whitelist. We "use" names here so vulture does not flag them as dead code.
# Regenerate candidates with: uv run vulture --make-whitelist
# Prefer removing dead code over adding entries here.

# --- Intentional: fields serialized by name, mirrored from backend DTOs ---
POPULATION  # GeoJSON property (data_management/seed_data_management/admin_areas/admin_area_geojson.py)
low  # WaterDischargeTimeSeriesEntry, mirrors exposure-geo-feature.dto.ts (pipelines/infra/data_types/dtos.py)
high  # WaterDischargeTimeSeriesEntry, mirrors exposure-geo-feature.dto.ts (pipelines/infra/data_types/dtos.py)

# --- To review: likely dead code, flagged when lowering Vulture min_confidence to 60 ---
# Remove the code and the entry here, or move the entry up with a justification.
load_processed_file  # unused function (data_management/seed_data_management/admin_areas/validate_admin_areas.py)
overlap_of_old_footprint  # unused variable (data_management/seed_data_management/flood/migrate_glofas_station_area_mapping.py)
AlertStation  # unused class (pipelines/flood/determine_alerts.py)
_.get_country_config  # unused method (pipelines/infra/config_reader.py)
first_pcode  # unused variable (pipelines/infra/data_provider.py)
SCHEDULED  # unused enum member (pipelines/infra/data_types/data_config_types.py)
DESTIN_E  # unused enum member (pipelines/infra/data_types/enums.py)
COMPOUND_FLOODS  # unused enum member (pipelines/infra/data_types/enums.py)
RED_CROSS_BRANCHES  # unused enum member (pipelines/infra/data_types/enums.py)
CLINICS  # unused enum member (pipelines/infra/data_types/enums.py)
BINARY  # unused enum member (pipelines/infra/data_types/loaded_data_types.py)
JSON_LIST  # unused enum member (pipelines/infra/data_types/loaded_data_types.py)
calculate_forecasts  # unused function (pipelines/infra/template_forecast.py)
ENTRY_START  # unused variable (pipelines/infra/utils/alert_integrity_checks.py)
ENTRY_END  # unused variable (pipelines/infra/utils/alert_integrity_checks.py)
GEFS_ENSEMBLE_COUNT  # unused variable (pipelines/tropical_cyclone/constants.py)
GEFS_WIND_MEMBER_IDS  # unused variable (pipelines/tropical_cyclone/constants.py)
GEFS_TRACK_MEMBER_IDS  # unused variable (pipelines/tropical_cyclone/constants.py)
ECMWF_PERTURBED_MEMBER_NUMBERS  # unused variable (pipelines/tropical_cyclone/constants.py)
ECMWF_TRACK_CONTROL_MEMBER_NUMBER  # unused variable (pipelines/tropical_cyclone/constants.py)
ECMWF_ENSEMBLE_COUNT  # unused variable (pipelines/tropical_cyclone/constants.py)
ECMWF_TRACK_FIX_INTERVAL_HOURS  # unused variable (pipelines/tropical_cyclone/constants.py)
_load_ecmwf_track_fixes  # unused function, kept as starting point for ECMWF multi-storm support (pipelines/tropical_cyclone/extract_track.py)
colorize_image_from_file  # unused function (shared/image_helpers.py)
