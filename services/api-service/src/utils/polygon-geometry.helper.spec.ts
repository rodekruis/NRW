import { getPolygonGeometryError } from '@api-service/src/utils/polygon-geometry.helper';

const LINEAR_RING = [
  [34.0, -14.0],
  [34.5, -14.0],
  [34.5, -13.5],
  [34.0, -14.0],
];
const TYPE_ERROR = 'the geometry type is not one of: Polygon, MultiPolygon';
const LINEAR_RING_ERROR =
  'a linear ring is not an array of at least 4 positions';

describe('getPolygonGeometryError', () => {
  it.each([
    { type: 'Polygon', coordinates: [LINEAR_RING] },
    { type: 'MultiPolygon', coordinates: [[LINEAR_RING], [LINEAR_RING]] },
  ])('should find no problem in a $type in EPSG:4326', (members) => {
    // Arrange
    const geometry = { ...members };

    // Act
    const result = getPolygonGeometryError(geometry);

    // Assert
    expect(result).toBeUndefined();
  });

  it('should ignore the elevation of a position', () => {
    // Arrange
    const linearRing = LINEAR_RING.map((position) => [...position, 1200]);
    const geometry = { type: 'Polygon', coordinates: [linearRing] };

    // Act
    const result = getPolygonGeometryError(geometry);

    // Assert
    expect(result).toBeUndefined();
  });

  it.each([
    { type: 'Point', coordinates: LINEAR_RING[0] },
    { type: 'LineString', coordinates: LINEAR_RING },
    { type: 'Feature', coordinates: [LINEAR_RING] },
    { type: undefined, coordinates: [LINEAR_RING] },
  ])('should report a geometry of type $type', (members) => {
    // Arrange
    const geometry = { ...members };

    // Act
    const result = getPolygonGeometryError(geometry);

    // Assert
    expect(result).toBe(TYPE_ERROR);
  });

  it.each([null, 'Polygon', 1])(
    'should report the value %p, which is not an object',
    (value) => {
      // Arrange
      const geometry: unknown = value;

      // Act
      const result = getPolygonGeometryError(geometry);

      // Assert
      expect(result).toBe('the geometry is not an object');
    },
  );

  it.each([
    { name: 'no coordinates', coordinates: undefined },
    { name: 'no linear rings', coordinates: [] },
  ])('should report a Polygon with $name', ({ coordinates }) => {
    // Arrange
    const geometry = { type: 'Polygon', coordinates };

    // Act
    const result = getPolygonGeometryError(geometry);

    // Assert
    expect(result).toBe(
      'the coordinates of a polygon are not an array of at least 1 linear ring',
    );
  });

  it('should report a MultiPolygon with no polygons', () => {
    // Arrange
    const geometry = { type: 'MultiPolygon', coordinates: [] };

    // Act
    const result = getPolygonGeometryError(geometry);

    // Assert
    expect(result).toBe(
      'the coordinates of the MultiPolygon are not an array of at least 1 polygon',
    );
  });

  it.each([
    {
      name: 'a Polygon with the coordinates of a MultiPolygon',
      type: 'Polygon',
      coordinates: [[LINEAR_RING]],
    },
    {
      name: 'a MultiPolygon with the coordinates of a Polygon',
      type: 'MultiPolygon',
      coordinates: [LINEAR_RING],
    },
    {
      name: 'a linear ring with fewer than 4 positions',
      type: 'Polygon',
      coordinates: [LINEAR_RING.slice(1)],
    },
    {
      name: 'a position with a value that is not a number',
      type: 'Polygon',
      coordinates: [[['34.0', -14.0], ...LINEAR_RING.slice(1)]],
    },
    {
      name: 'a position with only a longitude',
      type: 'Polygon',
      coordinates: [[...LINEAR_RING.slice(0, -1), [34.0]]],
    },
    {
      name: 'a problem in a polygon that is not the first polygon',
      type: 'MultiPolygon',
      coordinates: [[LINEAR_RING], [LINEAR_RING, []]],
    },
  ])('should report $name', ({ type, coordinates }) => {
    // Arrange
    const geometry = { type, coordinates };

    // Act
    const result = getPolygonGeometryError(geometry);

    // Assert
    expect(result).toBe(LINEAR_RING_ERROR);
  });

  it('should report a linear ring that is not closed', () => {
    // Arrange
    const linearRing = [...LINEAR_RING.slice(0, -1), [34.0, -13.5]];
    const geometry = { type: 'Polygon', coordinates: [linearRing] };

    // Act
    const result = getPolygonGeometryError(geometry);

    // Assert
    expect(result).toBe(
      'a linear ring is not closed: its first and last position differ',
    );
  });

  it('should report a position in metres', () => {
    // Arrange
    // The same area as LINEAR_RING, but in EPSG:3857
    const geometry = {
      type: 'Polygon',
      coordinates: [
        [
          [3784863, -1574216],
          [3840522, -1574216],
          [3840522, -1516914],
          [3784863, -1574216],
        ],
      ],
    };

    // Act
    const result = getPolygonGeometryError(geometry);

    // Assert
    expect(result).toContain(
      'position [3784863,-1574216] is not in the EPSG:4326 range',
    );
  });

  it("should report a 'crs' member, also when the coordinates are in the range", () => {
    // Arrange
    const geometry = {
      type: 'Polygon',
      coordinates: [LINEAR_RING],
      crs: { type: 'name', properties: { name: 'EPSG:4269' } },
    };

    // Act
    const result = getPolygonGeometryError(geometry);

    // Assert
    expect(result).toContain("'crs' member");
  });
});
