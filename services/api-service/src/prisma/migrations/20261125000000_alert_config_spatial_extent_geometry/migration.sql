-- Nullable: existing alert configs keep working without a geometry
ALTER TABLE "api-service"."alert-config" ADD COLUMN "spatialExtentGeometry" JSONB;
