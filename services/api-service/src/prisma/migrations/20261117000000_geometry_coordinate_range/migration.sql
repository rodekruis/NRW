-- Geometries are in EPSG:4326. The column type checks the SRID; these constraints check that the
-- coordinates are longitudes and latitudes in degrees, for example not metres of a projected CRS.
-- NOT VALID: the constraints apply to new and changed rows, and the migration cannot fail on existing rows.
ALTER TABLE "api-service"."admin-area" ADD CONSTRAINT "admin-area_geometry_coordinate_range_check" CHECK (
    public.ST_XMin("geometry") >= -180 AND public.ST_XMax("geometry") <= 180
    AND public.ST_YMin("geometry") >= -90 AND public.ST_YMax("geometry") <= 90
) NOT VALID;

ALTER TABLE "api-service"."geo-feature" ADD CONSTRAINT "geo-feature_geometry_coordinate_range_check" CHECK (
    public.ST_XMin("geometry") >= -180 AND public.ST_XMax("geometry") <= 180
    AND public.ST_YMin("geometry") >= -90 AND public.ST_YMax("geometry") <= 90
) NOT VALID;
