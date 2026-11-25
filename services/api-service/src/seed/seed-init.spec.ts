import { Logger } from '@nestjs/common';

jest.mock('@api-service/src/env', () => ({
  env: {
    USERCONFIG_API_SERVICE_EMAIL_ADMIN: 'admin@example.org',
    USERCONFIG_API_SERVICE_PASSWORD_ADMIN: 'password',
  },
}));

import { SEED_COUNTRIES } from '@api-service/src/seed/seed-data/seed-countries.const';
import { SeedInit } from '@api-service/src/seed/seed-init';

const COUNTRY_CODE = 'MWI';
const ADMIN_AREAS_PATH = '/admin-areas/processed/';
const STATION_THRESHOLDS_FILE = `${COUNTRY_CODE}_station_thresholds.json`;
const STATION_SPATIAL_EXTENTS_FILE = `${COUNTRY_CODE}_station_spatial_extents.geojson`;
// NAD83: the coordinates are in degrees, thus the range of the coordinates does not show this CRS
const DIFFERENT_CRS = { type: 'name', properties: { name: 'EPSG:4269' } };
const STATION_GEOMETRY = {
  type: 'Polygon',
  coordinates: [
    [
      [33, -14],
      [34, -14],
      [34, -13],
      [33, -14],
    ],
  ],
};

function createFeature(members: { crs?: unknown } = {}) {
  return {
    type: 'Feature',
    properties: { ADM0_PCODE: 'MW', ADM0_EN: 'Malawi' },
    geometry: {
      type: 'Polygon',
      coordinates: [
        [
          [33, -14],
          [34, -14],
          [34, -13],
          [33, -14],
        ],
      ],
    },
    ...members,
  };
}

function mockAdminAreaFiles(featureCollection: unknown): void {
  jest.spyOn(global, 'fetch').mockImplementation((input) =>
    Promise.resolve({
      ok: String(input).includes(ADMIN_AREAS_PATH),
      json: () => Promise.resolve(featureCollection),
    } as Response),
  );
}

function createStationThresholds(stationCode: string) {
  const deepestAdminLevel = SEED_COUNTRIES.find(
    (country) => country.countryCodeIso3 === COUNTRY_CODE,
  )?.deepestAdminLevel;
  return {
    station_code: stationCode,
    station_name: `Station ${stationCode}`,
    lat: -13.5,
    lon: 33.5,
    pcodes: { [String(deepestAdminLevel)]: ['MW10101'] },
    thresholds: [{ return_period: 5, threshold_value: 100 }],
  };
}

function createStationSpatialExtents(members: { crs?: unknown } = {}) {
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: { station_code: 'G1' },
        geometry: STATION_GEOMETRY,
      },
    ],
    ...members,
  };
}

// Files that are not in filesByName do not exist in the seed-data repo
function mockSeedRepoFiles(filesByName: Record<string, unknown>): void {
  jest.spyOn(global, 'fetch').mockImplementation((input) => {
    const filename = Object.keys(filesByName).find((name) =>
      String(input).endsWith(`/${name}`),
    );
    return Promise.resolve({
      ok: filename !== undefined,
      json: () => Promise.resolve(filename && filesByName[filename]),
    } as Response);
  });
}

describe('SeedInit', () => {
  let seedInit: SeedInit;
  let createAdminAreasMock: jest.Mock;
  let createAlertConfigsMock: jest.Mock;

  beforeEach(() => {
    jest.spyOn(Logger.prototype, 'log').mockImplementation();
    jest.spyOn(Logger.prototype, 'warn').mockImplementation();
    createAdminAreasMock = jest.fn();
    createAlertConfigsMock = jest.fn();

    const prisma = {
      $queryRaw: jest.fn().mockResolvedValue([]),
      user: { create: jest.fn() },
    } as never;
    const countriesService = { createCountries: jest.fn() } as never;
    const adminAreasService = {
      createAdminAreas: createAdminAreasMock,
    } as never;
    const alertConfigsService = {
      createAlertConfigs: createAlertConfigsMock,
    } as never;
    const geoFeaturesService = { createGeoFeatures: jest.fn() } as never;
    const layersService = { createLayer: jest.fn() } as never;
    const rastersService = {} as never;

    seedInit = new SeedInit(
      prisma,
      countriesService,
      adminAreasService,
      alertConfigsService,
      geoFeaturesService,
      layersService,
      rastersService,
    );
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  describe('run', () => {
    it.each([
      {
        location: 'the collection',
        featureCollection: {
          type: 'FeatureCollection',
          crs: DIFFERENT_CRS,
          features: [createFeature()],
        },
      },
      {
        location: 'a feature that is not the first feature',
        featureCollection: {
          type: 'FeatureCollection',
          features: [createFeature(), createFeature({ crs: DIFFERENT_CRS })],
        },
      },
      {
        location: 'a feature, with the value null',
        featureCollection: {
          type: 'FeatureCollection',
          features: [createFeature({ crs: null })],
        },
      },
    ])(
      "should reject an admin-area file with a 'crs' member in $location",
      async ({ featureCollection }) => {
        // Arrange
        mockAdminAreaFiles(featureCollection);

        // Act
        const run = seedInit.run({
          countryCodes: [COUNTRY_CODE],
          skipStaticRasters: true,
        });

        // Assert
        await expect(run).rejects.toThrow(
          `${COUNTRY_CODE}_adm0.json has a 'crs' member`,
        );
        expect(createAdminAreasMock).not.toHaveBeenCalled();
      },
    );

    it('should give a flood alert config the geometry of its station, and null when the station has no feature', async () => {
      // Arrange
      mockSeedRepoFiles({
        [STATION_THRESHOLDS_FILE]: [
          createStationThresholds('G1'),
          createStationThresholds('G2'),
        ],
        [STATION_SPATIAL_EXTENTS_FILE]: createStationSpatialExtents(),
      });

      // Act
      await seedInit.run({
        countryCodes: [COUNTRY_CODE],
        skipStaticRasters: true,
      });

      // Assert
      expect(createAlertConfigsMock).toHaveBeenCalledWith([
        expect.objectContaining({
          spatialExtentName: 'G1',
          spatialExtentGeometry: STATION_GEOMETRY,
        }),
        expect.objectContaining({
          spatialExtentName: 'G2',
          spatialExtentGeometry: null,
        }),
      ]);
    });

    it('should seed flood alert configs without a geometry when the country has no spatial extents file', async () => {
      // Arrange
      mockSeedRepoFiles({
        [STATION_THRESHOLDS_FILE]: [createStationThresholds('G1')],
      });

      // Act
      await seedInit.run({
        countryCodes: [COUNTRY_CODE],
        skipStaticRasters: true,
      });

      // Assert
      expect(createAlertConfigsMock).toHaveBeenCalledWith([
        expect.objectContaining({
          spatialExtentName: 'G1',
          spatialExtentGeometry: null,
        }),
      ]);
    });

    it("should reject a spatial extents file with a 'crs' member", async () => {
      // Arrange
      mockSeedRepoFiles({
        [STATION_THRESHOLDS_FILE]: [createStationThresholds('G1')],
        [STATION_SPATIAL_EXTENTS_FILE]: createStationSpatialExtents({
          crs: DIFFERENT_CRS,
        }),
      });

      // Act
      const run = seedInit.run({
        countryCodes: [COUNTRY_CODE],
        skipStaticRasters: true,
      });

      // Assert
      await expect(run).rejects.toThrow(
        `${STATION_SPATIAL_EXTENTS_FILE} has a 'crs' member`,
      );
      expect(createAlertConfigsMock).not.toHaveBeenCalled();
    });
  });
});
