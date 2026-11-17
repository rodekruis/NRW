import {
  getWgs84GeometryError,
  isExtentInWgs84Range,
} from '@api-service/src/utils/wgs84.helper';

describe('isExtentInWgs84Range', () => {
  it('should accept an extent at the limits of the range', () => {
    // Arrange
    const extent = { xmin: -180, ymin: -90, xmax: 180, ymax: 90 };

    // Act
    const result = isExtentInWgs84Range(extent);

    // Assert
    expect(result).toBe(true);
  });

  it('should reject an extent in metres', () => {
    // Arrange
    // Malawi in EPSG:3857
    const extent = {
      xmin: 3636800,
      ymin: -1938000,
      xmax: 3998600,
      ymax: -1049300,
    };

    // Act
    const result = isExtentInWgs84Range(extent);

    // Assert
    expect(result).toBe(false);
  });
});

describe('getWgs84GeometryError', () => {
  it('should find no problem in a geometry in EPSG:4326', () => {
    // Arrange
    const geometry = {
      type: 'MultiPolygon',
      coordinates: [
        [
          [
            [34.0, -14.0],
            [34.5, -14.0],
            [34.5, -13.5],
            [34.0, -14.0],
          ],
        ],
      ],
    };

    // Act
    const result = getWgs84GeometryError(geometry);

    // Assert
    expect(result).toBeUndefined();
  });

  it('should report a position in metres', () => {
    // Arrange
    const geometry = { type: 'Point', coordinates: [3800000, -1500000] };

    // Act
    const result = getWgs84GeometryError(geometry);

    // Assert
    expect(result).toContain(
      'position [3800000,-1500000] is not in the EPSG:4326 range',
    );
  });

  it('should report a position outside the range in a nested ring', () => {
    // Arrange
    const geometry = {
      type: 'MultiPolygon',
      coordinates: [
        [
          [
            [34.0, -14.0],
            [34.5, 91],
            [34.5, -13.5],
            [34.0, -14.0],
          ],
        ],
      ],
    };

    // Act
    const result = getWgs84GeometryError(geometry);

    // Assert
    expect(result).toContain('position [34.5,91]');
  });

  it("should report a 'crs' member, also when the coordinates are in the range", () => {
    // Arrange
    const geometry = {
      type: 'Point',
      coordinates: [100, 50],
      crs: { type: 'name', properties: { name: 'EPSG:3857' } },
    };

    // Act
    const result = getWgs84GeometryError(geometry);

    // Assert
    expect(result).toContain("'crs' member");
  });

  it('should report a problem in a member of a GeometryCollection', () => {
    // Arrange
    const geometry = {
      type: 'GeometryCollection',
      geometries: [
        { type: 'Point', coordinates: [34.5, -14.0] },
        { type: 'Point', coordinates: [3800000, -1500000] },
      ],
    };

    // Act
    const result = getWgs84GeometryError(geometry);

    // Assert
    expect(result).toContain('position [3800000,-1500000]');
  });

  it("should report a position in metres, also when the geometry has a 'geometries' member", () => {
    // Arrange
    // PostGIS reads the coordinates of a Point, not the 'geometries' member
    const geometry = {
      type: 'Point',
      coordinates: [3800000, -1500000],
      geometries: [],
    };

    // Act
    const result = getWgs84GeometryError(geometry);

    // Assert
    expect(result).toContain('position [3800000,-1500000]');
  });

  it('should report a position with a value that is not a number', () => {
    // Arrange
    // PostGIS reads this position as [0, 1000000]
    const geometry = { type: 'Point', coordinates: [[], 1000000] };

    // Act
    const result = getWgs84GeometryError(geometry);

    // Assert
    expect(result).toContain('position [[],1000000]');
  });

  it('should ignore the elevation of a position', () => {
    // Arrange
    const geometry = { type: 'Point', coordinates: [34.5, -14.0, 1200] };

    // Act
    const result = getWgs84GeometryError(geometry);

    // Assert
    expect(result).toBeUndefined();
  });

  it('should report coordinates that are not an array', () => {
    // Arrange
    const geometry = { type: 'Point', coordinates: 'invalid' };

    // Act
    const result = getWgs84GeometryError(geometry);

    // Assert
    expect(result).toBe('the coordinates are not an array');
  });

  it('should report a geometry that is not an object', () => {
    // Arrange
    const geometry = null;

    // Act
    const result = getWgs84GeometryError(geometry);

    // Assert
    expect(result).toBe('the geometry is not an object');
  });
});
