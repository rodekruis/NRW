import { NotFoundException } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import { Prisma } from '@prisma/client';

import { AlertConfigsRepository } from '@api-service/src/alert-configs/alert-configs.repository';
import { PrismaService } from '@api-service/src/prisma/prisma.service';
import {
  AlertClassificationLevel,
  HazardType,
} from '@api-service/src/shared-enums';

const alertConfigRowWithoutGeometry = {
  id: 1,
  created: new Date('2026-11-01T00:00:00Z'),
  updated: new Date('2026-11-01T00:00:00Z'),
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
  triggerAlertClass: null,
  triggerLeadTimeDuration: null,
};

const spatialExtentGeometry = {
  type: 'Polygon' as const,
  coordinates: [
    [
      [34.0, -14.0],
      [34.5, -14.0],
      [34.5, -13.5],
      [34.0, -14.0],
    ],
  ],
};

describe('AlertConfigsRepository', () => {
  let repository: AlertConfigsRepository;
  let findManyMock: jest.Mock;
  let updateMock: jest.Mock;

  beforeEach(async () => {
    findManyMock = jest.fn();
    updateMock = jest.fn();
    const module = await Test.createTestingModule({
      providers: [
        AlertConfigsRepository,
        {
          provide: PrismaService,
          useValue: {
            alertConfig: { findMany: findManyMock, update: updateMock },
          },
        },
      ],
    }).compile();

    repository = module.get(AlertConfigsRepository);
  });

  describe('getAlertConfigsWithoutGeometry', () => {
    it('should not load the spatial extent geometry', async () => {
      // Arrange
      findManyMock.mockResolvedValue([alertConfigRowWithoutGeometry]);

      // Act
      const alertConfigs = await repository.getAlertConfigsWithoutGeometry({
        countryCodeIso3: 'MWI',
        hazardType: HazardType.floods,
      });

      // Assert
      expect(findManyMock).toHaveBeenCalledWith(
        expect.objectContaining({
          where: { countryCodeIso3: 'MWI', hazardType: HazardType.floods },
          omit: { spatialExtentGeometry: true },
        }),
      );
      expect(alertConfigs).toEqual([alertConfigRowWithoutGeometry]);
      expect(alertConfigs[0]).not.toHaveProperty('spatialExtentGeometry');
    });
  });

  describe('getAlertConfigs', () => {
    it('should load the spatial extent geometry', async () => {
      // Arrange
      findManyMock.mockResolvedValue([
        { ...alertConfigRowWithoutGeometry, spatialExtentGeometry },
      ]);

      // Act
      const alertConfigs = await repository.getAlertConfigs({
        countryCodeIso3: 'MWI',
      });

      // Assert
      expect(findManyMock).toHaveBeenCalledWith(
        expect.not.objectContaining({ omit: expect.anything() }),
      );
      expect(alertConfigs[0].spatialExtentGeometry).toEqual(
        spatialExtentGeometry,
      );
    });
  });

  describe('updateAlertConfigOrThrow', () => {
    it('should update only the spatial extent geometry', async () => {
      // Arrange
      updateMock.mockResolvedValue({
        ...alertConfigRowWithoutGeometry,
        spatialExtentGeometry,
      });

      // Act
      const alertConfig = await repository.updateAlertConfigOrThrow({
        id: 1,
        alertConfigUpdateDto: { spatialExtentGeometry },
      });

      // Assert
      expect(updateMock).toHaveBeenCalledWith({
        where: { id: 1 },
        data: { spatialExtentGeometry },
      });
      expect(alertConfig.spatialExtentGeometry).toEqual(spatialExtentGeometry);
    });

    it('should store a database null when the spatial extent geometry is null', async () => {
      // Arrange
      updateMock.mockResolvedValue({
        ...alertConfigRowWithoutGeometry,
        spatialExtentGeometry: null,
      });

      // Act
      const alertConfig = await repository.updateAlertConfigOrThrow({
        id: 1,
        alertConfigUpdateDto: { spatialExtentGeometry: null },
      });

      // Assert
      expect(updateMock).toHaveBeenCalledWith({
        where: { id: 1 },
        data: { spatialExtentGeometry: Prisma.DbNull },
      });
      expect(alertConfig.spatialExtentGeometry).toBeNull();
    });

    it('should update only the properties in the body', async () => {
      // Arrange
      const severityClassLevels = [
        { label: AlertClassificationLevel.singleThreshold, threshold: 7 },
      ];
      updateMock.mockResolvedValue({
        ...alertConfigRowWithoutGeometry,
        spatialExtentGeometry: null,
        severityClassLevels,
      });

      // Act
      await repository.updateAlertConfigOrThrow({
        id: 1,
        alertConfigUpdateDto: { severityClassLevels, triggerAlertClass: null },
      });

      // Assert
      expect(updateMock).toHaveBeenCalledWith({
        where: { id: 1 },
        data: { severityClassLevels, triggerAlertClass: null },
      });
    });

    it('should throw a NotFoundException for an unknown id', async () => {
      // Arrange
      updateMock.mockRejectedValue(
        new Prisma.PrismaClientKnownRequestError('Record not found', {
          code: 'P2025',
          clientVersion: Prisma.prismaVersion.client,
        }),
      );

      // Act
      const act = repository.updateAlertConfigOrThrow({
        id: 999999,
        alertConfigUpdateDto: { spatialExtentGeometry: null },
      });

      // Assert
      await expect(act).rejects.toThrow(
        new NotFoundException('Alert config with id 999999 not found'),
      );
    });
  });
});
