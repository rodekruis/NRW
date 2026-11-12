import { PNG } from 'pngjs';

import { AlertsRepository } from '@api-service/src/alerts/alerts.repository';
import { AlertCreateDto } from '@api-service/src/alerts/dto/alert-create.dto';
import { PrismaService } from '@api-service/src/prisma/prisma.service';
import {
  ForecastSource,
  HazardType,
  LayerName,
} from '@api-service/src/shared-enums';

describe('AlertsRepository', () => {
  describe('createAlerts', () => {
    it('should store the coloured raster with Web Mercator rows', async () => {
      // Arrange
      // A single-pixel-wide raster of 4 cells from latitude 40 to 0.
      // Only the northern cell has data, so the data ends at latitude 30.
      const greyscalePng = new PNG({ width: 1, height: 4 });
      greyscalePng.data.set([255, 255, 255, 255]);
      const alertCreateDto: AlertCreateDto = {
        eventName: 'station-A',
        centroid: { latitude: 20, longitude: 0.5 },
        severity: [],
        exposure: {
          adminAreas: [],
          rasters: [
            {
              layer: LayerName.floodDepth,
              valueGreyscale: PNG.sync.write(greyscalePng).toString('base64'),
              extent: { xmin: 0, ymin: 0, xmax: 1, ymax: 40 },
            },
          ],
        },
      };
      const createAlert = jest
        .fn()
        .mockResolvedValue({ exposureAdminArea: [] });
      const prisma = {
        $transaction: (callback: (transaction: unknown) => unknown) =>
          callback({ alert: { create: createAlert } }),
      } as unknown as PrismaService;
      const repository = new AlertsRepository(prisma);

      // Act
      await repository.createAlerts({
        alertCreateDtos: [alertCreateDto],
        forecastMetadata: {
          countryCodeIso3: 'ETH',
          hazardType: HazardType.floods,
          forecastSources: [ForecastSource.glofasRiverDischarge],
          issuedAt: new Date('2026-03-20T12:00:00Z'),
        },
        eventIds: new Map(),
      });

      // Assert
      // Latitude 30 is at 28 % of the Web Mercator height from latitude 40 to 0,
      // and at 25 % of the latitude range.
      const [raster] =
        createAlert.mock.calls[0][0].data.exposureRasterData.create;
      const colouredPng = PNG.sync.read(
        Buffer.from(raster.valueColoured, 'base64'),
      );
      let visibleRowCount = 0;
      for (let row = 0; row < colouredPng.height; row++) {
        if (colouredPng.data[row * 4 + 3] > 0) {
          visibleRowCount++;
        }
      }
      expect(visibleRowCount / colouredPng.height).toBeCloseTo(0.28, 2);
    });
  });
});
