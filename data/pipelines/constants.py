# All geodata in the pipelines and in the seed data is in this CRS (WGS 84):
# x is the longitude and y is the latitude, in degrees.
DEFAULT_CRS = "EPSG:4326"
POPULATION_NODATA_VALUE = 0.0

# An admin area counts as part of a spatial extent geometry when at least this share of the admin
# area's own surface lies inside the geometry. Admin areas that only touch the edge, or have a sliver
# inside it, are left out. On the flood station areas, the admin areas kept still cover 98.8% or more
# of each area; the drought and compound-flood regions get back exactly the admin areas they were
# built from.
MINIMUM_ADMIN_AREA_SHARE_IN_SPATIAL_EXTENT = 0.01
