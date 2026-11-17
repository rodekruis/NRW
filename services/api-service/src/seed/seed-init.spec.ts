import { Logger } from '@nestjs/common';

jest.mock('@api-service/src/env', () => ({
  env: {
    USERCONFIG_API_SERVICE_EMAIL_ADMIN: 'admin@example.org',
    USERCONFIG_API_SERVICE_PASSWORD_ADMIN: 'password',
  },
}));

import { SeedInit } from '@api-service/src/seed/seed-init';

const COUNTRY_CODE = 'MWI';
const ADMIN_AREAS_PATH = '/admin-areas/processed/';
// NAD83: the coordinates are in degrees, thus the range of the coordinates does not show this CRS
const DIFFERENT_CRS = { type: 'name', properties: { name: 'EPSG:4269' } };

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

describe('SeedInit', () => {
  let seedInit: SeedInit;
  let createAdminAreasMock: jest.Mock;

  beforeEach(() => {
    jest.spyOn(Logger.prototype, 'log').mockImplementation();
    createAdminAreasMock = jest.fn();

    const prisma = {
      $queryRaw: jest.fn().mockResolvedValue([]),
      user: { create: jest.fn() },
    } as never;
    const countriesService = { createCountries: jest.fn() } as never;
    const adminAreasService = {
      createAdminAreas: createAdminAreasMock,
    } as never;
    const alertConfigsService = {} as never;
    const geoFeaturesService = {} as never;
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
  });
});
