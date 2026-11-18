import { extractPostgresErrorCode } from '@api-service/src/utils/extract-postgres-error-code.helper';

// All geodata in the api-service is in EPSG:4326 (WGS 84): x is the longitude
// and y is the latitude, in degrees. Coordinates in a projected CRS (metres)
// are almost always outside this range.
const MAX_LONGITUDE = 180;
const MAX_LATITUDE = 90;
const WGS84_RANGE_TEXT = `the EPSG:4326 range (longitude -${MAX_LONGITUDE} to ${MAX_LONGITUDE}, latitude -${MAX_LATITUDE} to ${MAX_LATITUDE})`;
// A position in an error message can be a value of any size
const MAX_POSITION_TEXT_LENGTH = 100;
// Postgres error code for a row that a check constraint rejects
const CHECK_VIOLATION_ERROR_CODE = '23514';

export function isExtentInWgs84Range(extent: {
  xmin: number;
  ymin: number;
  xmax: number;
  ymax: number;
}): boolean {
  return (
    isWgs84Position({ x: extent.xmin, y: extent.ymin }) &&
    isWgs84Position({ x: extent.xmax, y: extent.ymax })
  );
}

// Returns why a GeoJSON geometry is not in EPSG:4326, or undefined when it
// finds no problem. GeoJSON (RFC 7946) has no member that gives the CRS, thus
// the range of the coordinates is the only possible check of the CRS.
// This check gives a clear error before the database is changed. PostGIS reads
// some GeoJSON in a different way (e.g. member names in upper case), thus a
// check constraint on the geometry columns does the same check on the result.
export function getWgs84GeometryError(geometry: unknown): string | undefined {
  if (!isRecord(geometry)) {
    return 'the geometry is not an object';
  }

  // PostGIS uses a 'crs' member to set the SRID of the geometry
  if (geometry.crs !== undefined) {
    return "the geometry has a 'crs' member; give the coordinates in EPSG:4326 without a 'crs' member";
  }

  if (geometry.coordinates !== undefined) {
    const error = getCoordinatesError(geometry.coordinates);
    if (error) {
      return error;
    }
  }

  // GeometryCollection
  if (geometry.geometries !== undefined) {
    if (!Array.isArray(geometry.geometries)) {
      return "the 'geometries' member is not an array";
    }
    return geometry.geometries
      .map(getWgs84GeometryError)
      .find((error) => error !== undefined);
  }

  return undefined;
}

// Accepts only arrays of arrays and positions: PostGIS reads other values in
// the coordinates as 0, without an error.
function getCoordinatesError(coordinates: unknown): string | undefined {
  if (!Array.isArray(coordinates)) {
    return 'the coordinates are not an array';
  }

  if (coordinates.every(Array.isArray)) {
    for (const child of coordinates) {
      const error = getCoordinatesError(child);
      if (error) {
        return error;
      }
    }
    return undefined;
  }

  const [x, y] = coordinates;
  if (!isWgs84Position({ x, y })) {
    const position = JSON.stringify([x, y]).slice(0, MAX_POSITION_TEXT_LENGTH);
    return `position ${position} is not in ${WGS84_RANGE_TEXT}`;
  }
  return undefined;
}

// Returns the message for a geometry that the database did not accept. The
// only check constraints on the geometry columns are those on the coordinate range.
export function getGeometryDatabaseErrorMessage(error: {
  code: string;
  meta?: Record<string, unknown>;
}): string {
  return extractPostgresErrorCode(error) === CHECK_VIOLATION_ERROR_CODE
    ? `Invalid geometry: the coordinates are not in ${WGS84_RANGE_TEXT}`
    : 'Invalid geometry: could not parse GeoJSON';
}

function isWgs84Position({ x, y }: { x: unknown; y: unknown }): boolean {
  return (
    typeof x === 'number' &&
    typeof y === 'number' &&
    Math.abs(x) <= MAX_LONGITUDE &&
    Math.abs(y) <= MAX_LATITUDE
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}
