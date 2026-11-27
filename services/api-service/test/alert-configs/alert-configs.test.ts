import { HttpStatus } from '@nestjs/common';
import * as request from 'supertest';

import { env } from '@api-service/src/env';
import {
  AlertClass,
  AlertClassificationLevel,
  HazardType,
} from '@api-service/src/shared-enums';
import {
  getAccessToken,
  getServer,
  resetDB,
} from '@api-service/test/helpers/utility.helper';

describe('/ Alert Configs', () => {
  let accessToken: string;

  beforeAll(async () => {
    await resetDB({ countryCodes: ['MWI'], resetIdentifier: __filename });
    accessToken = await getAccessToken();
  });

  const validAlertConfig = {
    countryCodeIso3: 'MWI',
    hazardType: HazardType.floods,
    spatialExtentName: 'TEST_STATION',
    temporalExtents: [{ 'lead-time-spectrum': ['0-day', '1-day', '2-day'] }],
    severityClassLevels: [
      { label: AlertClassificationLevel.low, threshold: 100 },
      { label: AlertClassificationLevel.medium, threshold: 200 },
      { label: AlertClassificationLevel.high, threshold: 400 },
    ],
    probabilityClassLevels: [
      { label: AlertClassificationLevel.low, threshold: 0.5 },
      { label: AlertClassificationLevel.medium, threshold: 0.65 },
      { label: AlertClassificationLevel.high, threshold: 0.85 },
    ],
    triggerAlertClass: AlertClass.high,
    triggerLeadTimeDuration: 'P7D',
  };

  const spatialExtentGeometry = {
    type: 'Polygon',
    coordinates: [
      [
        [34.0, -14.0],
        [34.5, -14.0],
        [34.5, -13.5],
        [34.0, -14.0],
      ],
    ],
  };

  function getFloodAlertConfigs(): request.Test {
    return getServer()
      .get('/alert-configs')
      .query({ countryCodeIso3: 'MWI', hazardType: HazardType.floods })
      .set('Cookie', [accessToken]);
  }

  // Closed and in range, but invalid in PostGIS: the edges of the ring cross at (34.25, -13.75)
  const bowTiePolygon = {
    type: 'Polygon',
    coordinates: [
      [
        [34.0, -14.0],
        [34.5, -13.5],
        [34.5, -14.0],
        [34.0, -13.5],
        [34.0, -14.0],
      ],
    ],
  };
  const polygonWithHoleOutsideShell = {
    type: 'Polygon',
    coordinates: [
      spatialExtentGeometry.coordinates[0],
      [
        [35.0, -14.0],
        [35.1, -14.0],
        [35.1, -13.9],
        [35.0, -14.0],
      ],
    ],
  };

  describe('POST /alert-configs', () => {
    it('should create alert configs', async () => {
      const response = await getServer()
        .post('/alert-configs')
        .set('Cookie', [accessToken])
        .send([validAlertConfig]);

      expect(response.status).toBe(HttpStatus.CREATED);
      expect(response.body[0].id).toBeDefined();
      expect(response.body[0].countryCodeIso3).toBe('MWI');
      expect(response.body[0].hazardType).toBe(HazardType.floods);
      expect(response.body[0].spatialExtentName).toBe('TEST_STATION');
      expect(response.body[0]).not.toHaveProperty('spatialExtentPlaceCodes');
    });

    it('should create and return an alert config with a spatial extent geometry', async () => {
      // Arrange
      const alertConfig = {
        ...validAlertConfig,
        spatialExtentName: 'GEOMETRY_STATION',
        spatialExtentGeometry,
      };

      // Act
      const createResponse = await getServer()
        .post('/alert-configs')
        .set('Cookie', [accessToken])
        .send([alertConfig]);
      const getResponse = await getFloodAlertConfigs();

      // Assert
      expect(createResponse.status).toBe(HttpStatus.CREATED);
      expect(createResponse.body[0].spatialExtentGeometry).toEqual(
        spatialExtentGeometry,
      );
      const createdAlertConfig = getResponse.body.find(
        (config: { id: number }) => config.id === createResponse.body[0].id,
      );
      expect(createdAlertConfig.spatialExtentGeometry).toEqual(
        spatialExtentGeometry,
      );
    });

    it('should create and return an alert config without a spatial extent geometry', async () => {
      // Arrange
      const alertConfig = {
        ...validAlertConfig,
        spatialExtentName: 'NO_GEOMETRY_STATION',
      };

      // Act
      const createResponse = await getServer()
        .post('/alert-configs')
        .set('Cookie', [accessToken])
        .send([alertConfig]);
      const getResponse = await getFloodAlertConfigs();

      // Assert
      expect(createResponse.status).toBe(HttpStatus.CREATED);
      expect(createResponse.body[0].spatialExtentGeometry).toBeNull();
      const createdAlertConfig = getResponse.body.find(
        (config: { id: number }) => config.id === createResponse.body[0].id,
      );
      expect(createdAlertConfig.spatialExtentGeometry).toBeNull();
    });

    it.each([
      {
        name: 'a Point',
        invalidGeometry: { type: 'Point', coordinates: [34.0, -14.0] },
      },
      {
        name: 'a Polygon that is not closed',
        invalidGeometry: {
          type: 'Polygon',
          coordinates: [
            [
              ...spatialExtentGeometry.coordinates[0].slice(0, -1),
              [34.0, -13.5],
            ],
          ],
        },
      },
      {
        // The same area as spatialExtentGeometry, but in EPSG:3857
        name: 'a Polygon in metres',
        invalidGeometry: {
          type: 'Polygon',
          coordinates: [
            [
              [3784863, -1574216],
              [3840522, -1574216],
              [3840522, -1516914],
              [3784863, -1574216],
            ],
          ],
        },
      },
      { name: 'a string', invalidGeometry: 'Polygon' },
      { name: 'a self-intersecting Polygon', invalidGeometry: bowTiePolygon },
      {
        name: 'a Polygon with a hole outside its shell',
        invalidGeometry: polygonWithHoleOutsideShell,
      },
    ])(
      'should reject a spatial extent geometry that is $name',
      async ({ invalidGeometry }) => {
        // Arrange
        const spatialExtentName = 'INVALID_GEOMETRY_STATION';
        const alertConfig = {
          ...validAlertConfig,
          spatialExtentName,
          spatialExtentGeometry: invalidGeometry,
        };

        // Act
        const createResponse = await getServer()
          .post('/alert-configs')
          .set('Cookie', [accessToken])
          .send([alertConfig]);
        const getResponse = await getFloodAlertConfigs();

        // Assert
        expect(createResponse.status).toBe(HttpStatus.BAD_REQUEST);
        const spatialExtentNames = getResponse.body.map(
          (config: { spatialExtentName: string }) => config.spatialExtentName,
        );
        expect(spatialExtentNames).not.toContain(spatialExtentName);
      },
    );

    it('should reject invalid hazard type', async () => {
      const response = await getServer()
        .post('/alert-configs')
        .set('Cookie', [accessToken])
        .send([{ ...validAlertConfig, hazardType: 'invalid' }]);

      expect(response.status).toBe(HttpStatus.BAD_REQUEST);
    });

    it('should return 400 for non-existent country', async () => {
      const response = await getServer()
        .post('/alert-configs')
        .set('Cookie', [accessToken])
        .send([{ ...validAlertConfig, countryCodeIso3: 'XXX' }]);

      expect(response.status).toBe(HttpStatus.BAD_REQUEST);
    });
  });

  describe('GET /alert-configs', () => {
    it('should return alert configs filtered by country and hazard type', async () => {
      const response = await getServer()
        .get('/alert-configs')
        .query({ countryCodeIso3: 'MWI', hazardType: HazardType.floods })
        .set('Cookie', [accessToken]);

      expect(response.status).toBe(HttpStatus.OK);
      expect(response.body.length).toBeGreaterThan(0);

      for (const config of response.body) {
        expect(config.countryCodeIso3).toBe('MWI');
        expect(config.hazardType).toBe(HazardType.floods);
      }
    });

    it('should return empty array for country with no configs of given type', async () => {
      const response = await getServer()
        .get('/alert-configs')
        .query({ countryCodeIso3: 'XXX', hazardType: HazardType.drought })
        .set('Cookie', [accessToken]);

      expect(response.status).toBe(HttpStatus.OK);
      expect(response.body).toEqual([]);
    });

    it('should reject invalid hazard type query parameter', async () => {
      const response = await getServer()
        .get('/alert-configs')
        .query({ countryCodeIso3: 'MWI', hazardType: 'typhoon' })
        .set('Cookie', [accessToken]);

      expect(response.status).toBe(HttpStatus.BAD_REQUEST);
    });
  });

  describe('PATCH /alert-configs/:id', () => {
    let alertConfigId: number;

    beforeAll(async () => {
      const createResponse = await getServer()
        .post('/alert-configs')
        .set('Cookie', [accessToken])
        .send([{ ...validAlertConfig, spatialExtentName: 'TO_PATCH_STATION' }]);
      alertConfigId = createResponse.body[0].id;
    });

    function patchAlertConfig({
      id,
      body,
    }: {
      id: number;
      body: Record<string, unknown>;
    }): request.Test {
      return getServer()
        .patch(`/alert-configs/${id}`)
        .set('Cookie', [accessToken])
        .send(body);
    }

    it('should update the spatial extent geometry and keep the other fields', async () => {
      // Arrange
      const body = {
        spatialExtentGeometry,
        spatialExtentName: 'NOT_PATCHABLE',
      };

      // Act
      const patchResponse = await patchAlertConfig({ id: alertConfigId, body });
      const getResponse = await getFloodAlertConfigs();

      // Assert
      expect(patchResponse.status).toBe(HttpStatus.OK);
      expect(patchResponse.body.id).toBe(alertConfigId);
      expect(patchResponse.body.spatialExtentGeometry).toEqual(
        spatialExtentGeometry,
      );
      expect(patchResponse.body.spatialExtentName).toBe('TO_PATCH_STATION');
      const patchedAlertConfig = getResponse.body.find(
        (config: { id: number }) => config.id === alertConfigId,
      );
      expect(patchedAlertConfig.spatialExtentGeometry).toEqual(
        spatialExtentGeometry,
      );
    });

    it('should remove the spatial extent geometry when it is null', async () => {
      // Arrange
      await patchAlertConfig({
        id: alertConfigId,
        body: { spatialExtentGeometry },
      });

      // Act
      const patchResponse = await patchAlertConfig({
        id: alertConfigId,
        body: { spatialExtentGeometry: null },
      });
      const getResponse = await getFloodAlertConfigs();

      // Assert
      expect(patchResponse.status).toBe(HttpStatus.OK);
      expect(patchResponse.body.spatialExtentGeometry).toBeNull();
      const patchedAlertConfig = getResponse.body.find(
        (config: { id: number }) => config.id === alertConfigId,
      );
      expect(patchedAlertConfig.spatialExtentGeometry).toBeNull();
    });

    it.each([
      {
        name: 'a Point',
        body: {
          spatialExtentGeometry: { type: 'Point', coordinates: [34.0, -14.0] },
        },
      },
      { name: 'a string', body: { spatialExtentGeometry: 'Polygon' } },
      {
        name: 'self-intersecting',
        body: { spatialExtentGeometry: bowTiePolygon },
      },
    ])(
      'should return 400 when the spatial extent geometry is $name',
      async ({ body }) => {
        // Arrange
        await patchAlertConfig({
          id: alertConfigId,
          body: { spatialExtentGeometry },
        });

        // Act
        const patchResponse = await patchAlertConfig({
          id: alertConfigId,
          body,
        });
        const getResponse = await getFloodAlertConfigs();

        // Assert
        expect(patchResponse.status).toBe(HttpStatus.BAD_REQUEST);
        const alertConfig = getResponse.body.find(
          (config: { id: number }) => config.id === alertConfigId,
        );
        expect(alertConfig.spatialExtentGeometry).toEqual(
          spatialExtentGeometry,
        );
      },
    );

    it('should update other properties and keep the spatial extent geometry', async () => {
      // Arrange
      await patchAlertConfig({
        id: alertConfigId,
        body: { spatialExtentGeometry },
      });
      const severityClassLevels = [
        { label: AlertClassificationLevel.singleThreshold, threshold: 7 },
      ];

      // Act
      const patchResponse = await patchAlertConfig({
        id: alertConfigId,
        body: { severityClassLevels, triggerLeadTimeDuration: 'P5D' },
      });

      // Assert
      expect(patchResponse.status).toBe(HttpStatus.OK);
      expect(patchResponse.body.severityClassLevels).toEqual(
        severityClassLevels,
      );
      expect(patchResponse.body.triggerLeadTimeDuration).toBe('P5D');
      expect(patchResponse.body.spatialExtentGeometry).toEqual(
        spatialExtentGeometry,
      );
    });

    it('should return 400 for invalid other properties', async () => {
      // Arrange
      const body = { severityClassLevels: 'high' };

      // Act
      const patchResponse = await patchAlertConfig({ id: alertConfigId, body });

      // Assert
      expect(patchResponse.status).toBe(HttpStatus.BAD_REQUEST);
    });

    it('should return 404 for a non-existent id', async () => {
      // Arrange
      const body = { spatialExtentGeometry };

      // Act
      const response = await patchAlertConfig({ id: 999999, body });

      // Assert
      expect(response.status).toBe(HttpStatus.NOT_FOUND);
    });

    it('should reject unauthenticated requests', async () => {
      // Arrange
      const body = { spatialExtentGeometry };

      // Act
      const response = await getServer()
        .patch(`/alert-configs/${alertConfigId}`)
        .send(body);

      // Assert
      expect(response.status).toBe(HttpStatus.UNAUTHORIZED);
    });

    it('should reject requests with only the pipeline API key', async () => {
      // Arrange
      const body = { spatialExtentGeometry };

      // Act
      const response = await getServer()
        .patch(`/alert-configs/${alertConfigId}`)
        .set('x-api-key', env.PIPELINE_API_KEY!)
        .send(body);

      // Assert
      expect(response.status).toBe(HttpStatus.UNAUTHORIZED);
    });
  });

  describe('DELETE /alert-configs/:id', () => {
    it('should delete an existing alert config', async () => {
      const createResponse = await getServer()
        .post('/alert-configs')
        .set('Cookie', [accessToken])
        .send([
          {
            ...validAlertConfig,
            spatialExtentName: 'TO_DELETE_STATION',
          },
        ]);

      expect(createResponse.status).toBe(HttpStatus.CREATED);
      const id = createResponse.body[0].id;

      const deleteResponse = await getServer()
        .delete(`/alert-configs/${id}`)
        .set('Cookie', [accessToken]);

      expect(deleteResponse.status).toBe(HttpStatus.NO_CONTENT);

      const getResponse = await getServer()
        .get('/alert-configs')
        .query({ countryCodeIso3: 'MWI', hazardType: HazardType.floods })
        .set('Cookie', [accessToken]);

      const deleted = getResponse.body.find((c: { id: number }) => c.id === id);
      expect(deleted).toBeUndefined();
    });

    it('should return 404 for non-existent id', async () => {
      const response = await getServer()
        .delete('/alert-configs/999999')
        .set('Cookie', [accessToken]);

      expect(response.status).toBe(HttpStatus.NOT_FOUND);
    });
  });
});
