import type { MultiPolygon, Polygon } from 'geojson';

import { getWgs84GeometryError } from '@api-service/src/utils/wgs84.helper';

export const POLYGON_GEOMETRY_TYPES = [
  'Polygon',
  'MultiPolygon',
] as const satisfies (Polygon | MultiPolygon)['type'][];

type PolygonGeometryType = (typeof POLYGON_GEOMETRY_TYPES)[number];

// A linear ring is closed: its first and last position are the same (RFC 7946, section 3.1.6)
const MIN_LINEAR_RING_POSITIONS = 4;
// A position is [longitude, latitude], with an optional altitude
const MIN_POSITION_LENGTH = 2;

interface GeometryMembers {
  readonly type?: unknown;
  readonly coordinates?: unknown;
}

// Returns why a value is not a GeoJSON Polygon or MultiPolygon geometry in
// EPSG:4326, or undefined when it finds no problem.
// A geometry in a JSON column gets no check of PostGIS, thus this is the only check.
export function getPolygonGeometryError(geometry: unknown): string | undefined {
  if (typeof geometry !== 'object' || geometry === null) {
    return 'the geometry is not an object';
  }

  const { type, coordinates }: GeometryMembers = geometry;
  if (!isPolygonGeometryType(type)) {
    return `the geometry type is not one of: ${POLYGON_GEOMETRY_TYPES.join(', ')}`;
  }

  const coordinatesError =
    type === 'Polygon'
      ? getPolygonCoordinatesError(coordinates)
      : getMultiPolygonCoordinatesError(coordinates);

  // Checks the 'crs' member and the range of the coordinates
  return coordinatesError ?? getWgs84GeometryError(geometry);
}

function isPolygonGeometryType(type: unknown): type is PolygonGeometryType {
  return POLYGON_GEOMETRY_TYPES.some(
    (polygonGeometryType) => polygonGeometryType === type,
  );
}

function getMultiPolygonCoordinatesError(
  coordinates: unknown,
): string | undefined {
  if (!Array.isArray(coordinates) || coordinates.length === 0) {
    return 'the coordinates of the MultiPolygon are not an array of at least 1 polygon';
  }
  return coordinates
    .map(getPolygonCoordinatesError)
    .find((error) => error !== undefined);
}

function getPolygonCoordinatesError(coordinates: unknown): string | undefined {
  if (!Array.isArray(coordinates) || coordinates.length === 0) {
    return 'the coordinates of a polygon are not an array of at least 1 linear ring';
  }
  return coordinates
    .map(getLinearRingError)
    .find((error) => error !== undefined);
}

function getLinearRingError(linearRing: unknown): string | undefined {
  if (
    !Array.isArray(linearRing) ||
    linearRing.length < MIN_LINEAR_RING_POSITIONS ||
    !linearRing.every(isPosition)
  ) {
    return `a linear ring is not an array of at least ${MIN_LINEAR_RING_POSITIONS} positions`;
  }

  const firstPosition = linearRing[0];
  const lastPosition = linearRing[linearRing.length - 1];
  const isClosed =
    firstPosition.length === lastPosition.length &&
    firstPosition.every((value, index) => value === lastPosition[index]);
  if (!isClosed) {
    return 'a linear ring is not closed: its first and last position differ';
  }
  return undefined;
}

function isPosition(position: unknown): position is number[] {
  return (
    Array.isArray(position) &&
    position.length >= MIN_POSITION_LENGTH &&
    position.every((value) => typeof value === 'number')
  );
}
