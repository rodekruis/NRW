-- Schema only. Right after deploy, production gets its geometries from
-- data/data_management/api_data_management/update_alert_config_spatial_extents_in_api.py
-- through PATCH /alert-configs/:id.

-- Nullable: an alert config without a geometry covers the whole country
ALTER TABLE "api-service"."alert-config" ADD COLUMN "spatialExtentGeometry" JSONB;

ALTER TABLE "api-service"."alert-config" DROP COLUMN "spatialExtentPlaceCodes";
