import { BadRequestException } from '@nestjs/common';
import { Test } from '@nestjs/testing';

import { GeoFeatureType } from '@api-service/src/geo-features/enum/geo-feature-type.enum';
import { GeoFeaturesRepository } from '@api-service/src/geo-features/geo-features.repository';
import { GeoFeaturesService } from '@api-service/src/geo-features/geo-features.service';
import { LayerName } from '@api-service/src/shared-enums';

const validGeoFeature = {
  countryCodeIso3: 'MWI',
  featureType: GeoFeatureType.point,
  layer: LayerName.glofasStations,
  referenceId: 'TEST_STATION_01',
  geometry: { type: 'Point', coordinates: [34.5, -14.0] },
};

// The same point as in validGeoFeature, but in EPSG:3857
const geometryInMetres = { type: 'Point', coordinates: [3840522, -1574216] };

describe('GeoFeaturesService', () => {
  let service: GeoFeaturesService;
  let repository: jest.Mocked<GeoFeaturesRepository>;

  beforeEach(async () => {
    const module = await Test.createTestingModule({
      providers: [
        GeoFeaturesService,
        {
          provide: GeoFeaturesRepository,
          useValue: {
            createGeoFeatures: jest.fn(),
            updateGeoFeatureOrThrow: jest.fn(),
          },
        },
      ],
    }).compile();

    service = module.get(GeoFeaturesService);
    repository = module.get(GeoFeaturesRepository);
  });

  describe('createGeoFeatures', () => {
    it('should create no geo-features when one geometry is not in EPSG:4326', async () => {
      // Arrange
      const geoFeatures = [
        validGeoFeature,
        {
          ...validGeoFeature,
          referenceId: 'TEST_STATION_02',
          geometry: geometryInMetres,
        },
      ];

      // Act
      const act = service.createGeoFeatures(geoFeatures);

      // Assert
      await expect(act).rejects.toThrow(
        new BadRequestException(
          "Invalid geometry for geo-feature 'TEST_STATION_02': position [3840522,-1574216] is not in the EPSG:4326 range (longitude -180 to 180, latitude -90 to 90)",
        ),
      );
      expect(repository.createGeoFeatures).not.toHaveBeenCalled();
    });
  });

  describe('updateGeoFeatureOrThrow', () => {
    it('should reject a geometry that is not in EPSG:4326', async () => {
      // Arrange
      const geoFeatureUpdateDto = { geometry: geometryInMetres };

      // Act
      const act = service.updateGeoFeatureOrThrow({
        id: 1,
        geoFeatureUpdateDto,
      });

      // Assert
      await expect(act).rejects.toThrow(BadRequestException);
      expect(repository.updateGeoFeatureOrThrow).not.toHaveBeenCalled();
    });
  });
});
