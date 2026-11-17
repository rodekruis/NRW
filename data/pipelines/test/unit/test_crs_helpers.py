import pytest
from fiona.crs import CRS as FionaCrs
from rasterio.crs import CRS as RasterioCrs
from shared.crs_helpers import validate_crs

from pipelines.constants import DEFAULT_CRS

# The text of a .prj file that ArcGIS writes, e.g. in the admin-area shapefiles of HDX
ESRI_WGS84_WKT = (
    'GEOGCS["GCS_WGS_1984",DATUM["D_WGS_1984",'
    'SPHEROID["WGS_1984",6378137.0,298.257223563]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)
# NAD83: the coordinates are in degrees, thus only the CRS of the source shows the difference
ESRI_NAD83_WKT = (
    'GEOGCS["GCS_North_American_1983",DATUM["D_North_American_1983",'
    'SPHEROID["GRS_1980",6378137.0,298.257222101]],'
    'PRIMEM["Greenwich",0.0],UNIT["Degree",0.0174532925199433]]'
)
UNKNOWN_DATUM_WKT = (
    'GEOGCS["unknown",DATUM["unknown",'
    'SPHEROID["WGS 84",6378137,298.257223563]],'
    'PRIMEM["Greenwich",0],UNIT["degree",0.0174532925199433]]'
)


@pytest.mark.parametrize(
    "crs",
    [
        pytest.param(DEFAULT_CRS, id="string"),
        pytest.param(RasterioCrs.from_epsg(4326), id="rasterio-epsg-code"),
        pytest.param(RasterioCrs.from_wkt(ESRI_WGS84_WKT), id="rasterio-esri-wkt"),
        pytest.param(FionaCrs.from_epsg(4326), id="fiona-epsg-code"),
        pytest.param(FionaCrs.from_wkt(ESRI_WGS84_WKT), id="fiona-esri-wkt"),
    ],
)
def test_accepts_each_form_of_the_default_crs(crs: object):
    # Act, Assert: no exception
    validate_crs(crs, "Source")


@pytest.mark.parametrize(
    "crs",
    [
        pytest.param(None, id="no-crs"),
        pytest.param(FionaCrs(), id="empty-crs-object"),
        pytest.param("epsg:4326", id="string-that-is-not-exact"),
        pytest.param(RasterioCrs.from_epsg(3857), id="projected-crs"),
        pytest.param(FionaCrs.from_wkt(ESRI_NAD83_WKT), id="different-datum"),
        pytest.param(RasterioCrs.from_wkt(UNKNOWN_DATUM_WKT), id="unknown-datum"),
    ],
)
def test_raises_for_a_crs_that_is_not_the_default_crs(crs: object):
    # Act, Assert
    with pytest.raises(ValueError, match="but only EPSG:4326 is supported"):
        validate_crs(crs, "Source")
