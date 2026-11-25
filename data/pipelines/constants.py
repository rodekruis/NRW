# All geodata in the pipelines and in the seed data is in this CRS (WGS 84):
# x is the longitude and y is the latitude, in degrees.
DEFAULT_CRS = "EPSG:4326"
POPULATION_NODATA_VALUE = 0.0

# An admin area belongs to an alert config's spatial extent geometry when at least this share of
# the admin area lies inside it. It drops the slivers along the edge: on the flood station areas it
# keeps admin areas covering 98.8% or more of each area, and the drought regions get back exactly
# the admin areas they were built from.
MINIMUM_ADMIN_AREA_SHARE_IN_SPATIAL_EXTENT = 0.01
