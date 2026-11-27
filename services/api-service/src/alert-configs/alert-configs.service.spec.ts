import { BadRequestException } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import type { Polygon } from 'geojson';

import { AlertConfigsRepository } from '@api-service/src/alert-configs/alert-configs.repository';
import { AlertConfigsService } from '@api-service/src/alert-configs/alert-configs.service';
import { AlertConfigCreateDto } from '@api-service/src/alert-configs/dto/alert-config-create.dto';
import {
  AlertClassificationLevel,
  HazardType,
} from '@api-service/src/shared-enums';

const alertConfigWithoutGeometry: AlertConfigCreateDto = {
  countryCodeIso3: 'MWI',
  hazardType: HazardType.floods,
  spatialExtentName: 'G1',
  temporalExtents: [{ 'lead-time-spectrum': ['0-day', '1-day'] }],
  severityClassLevels: [
    { label: AlertClassificationLevel.singleThreshold, threshold: 5 },
  ],
  probabilityClassLevels: [
    { label: AlertClassificationLevel.singleThreshold, threshold: 0.6 },
  ],
};

const spatialExtentGeometry: Polygon = {
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

const alertConfigWithGeometry: AlertConfigCreateDto = {
  ...alertConfigWithoutGeometry,
  spatialExtentName: 'G2',
  spatialExtentGeometry,
};

describe('AlertConfigsService', () => {
  let service: AlertConfigsService;
  let repository: jest.Mocked<AlertConfigsRepository>;

  beforeEach(async () => {
    const module = await Test.createTestingModule({
      providers: [
        AlertConfigsService,
        {
          provide: AlertConfigsRepository,
          useValue: {
            createAlertConfigs: jest.fn().mockResolvedValue([]),
            updateAlertConfigOrThrow: jest.fn(),
          },
        },
      ],
    }).compile();

    service = module.get(AlertConfigsService);
    repository = module.get(AlertConfigsRepository);
  });

  describe('createAlertConfigs', () => {
    it('should create alert configs with and without a spatial extent geometry', async () => {
      // Arrange
      const alertConfigs = [
        alertConfigWithGeometry,
        alertConfigWithoutGeometry,
        { ...alertConfigWithoutGeometry, spatialExtentGeometry: null },
      ];

      // Act
      await service.createAlertConfigs(alertConfigs);

      // Assert
      expect(repository.createAlertConfigs).toHaveBeenCalledWith(alertConfigs);
    });

    it('should create no alert configs when one spatial extent geometry is not a Polygon or MultiPolygon', async () => {
      // Arrange
      const point = { type: 'Point', coordinates: [34.0, -14.0] };
      const alertConfigs = [
        alertConfigWithGeometry,
        {
          ...alertConfigWithoutGeometry,
          spatialExtentName: 'G3',
          // The request body can have any JSON object
          spatialExtentGeometry: point as never,
        },
      ];

      // Act
      const act = service.createAlertConfigs(alertConfigs);

      // Assert
      await expect(act).rejects.toThrow(
        new BadRequestException(
          "Invalid spatialExtentGeometry for alert config 'G3': the geometry type is not one of: Polygon, MultiPolygon",
        ),
      );
      expect(repository.createAlertConfigs).not.toHaveBeenCalled();
    });
  });

  describe('updateAlertConfigOrThrow', () => {
    it.each([
      { label: 'a geometry', alertConfigUpdateDto: { spatialExtentGeometry } },
      { label: 'null', alertConfigUpdateDto: { spatialExtentGeometry: null } },
    ])(
      'should update the spatial extent geometry to $label',
      async ({ alertConfigUpdateDto }) => {
        // Arrange
        const id = 1;

        // Act
        await service.updateAlertConfigOrThrow({ id, alertConfigUpdateDto });

        // Assert
        expect(repository.updateAlertConfigOrThrow).toHaveBeenCalledWith({
          id,
          alertConfigUpdateDto,
        });
      },
    );

    it('should not update when the spatial extent geometry is not a Polygon or MultiPolygon', async () => {
      // Arrange
      const point = { type: 'Point', coordinates: [34.0, -14.0] };

      // Act
      const act = service.updateAlertConfigOrThrow({
        id: 1,
        // The request body can have any JSON object
        alertConfigUpdateDto: { spatialExtentGeometry: point as never },
      });

      // Assert
      await expect(act).rejects.toThrow(
        new BadRequestException(
          'Invalid spatialExtentGeometry for alert config with id 1: the geometry type is not one of: Polygon, MultiPolygon',
        ),
      );
      expect(repository.updateAlertConfigOrThrow).not.toHaveBeenCalled();
    });
  });
});
