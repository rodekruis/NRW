import { BadRequestException } from '@nestjs/common';
import { Test } from '@nestjs/testing';

import { AdminAreasRepository } from '@api-service/src/admin-areas/admin-areas.repository';
import { AdminAreasService } from '@api-service/src/admin-areas/admin-areas.service';

const validAdminArea = {
  placeCode: 'TEST01',
  adminLevel: 1,
  nameEn: 'Test Admin Area',
  countryCodeIso3: 'MWI',
  placeCodeLevel0: 'MW',
  geometry: {
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
  },
};

// The same area as validAdminArea, but in EPSG:3857
const geometryInMetres = {
  type: 'MultiPolygon',
  coordinates: [
    [
      [
        [3784863, -1574216],
        [3840522, -1574216],
        [3840522, -1516914],
        [3784863, -1574216],
      ],
    ],
  ],
};

describe('AdminAreasService', () => {
  let service: AdminAreasService;
  let repository: jest.Mocked<AdminAreasRepository>;

  beforeEach(async () => {
    const module = await Test.createTestingModule({
      providers: [
        AdminAreasService,
        {
          provide: AdminAreasRepository,
          useValue: {
            getAdminAreas: jest.fn().mockResolvedValue({
              type: 'FeatureCollection',
              features: [],
              numberReturned: 0,
            }),
            createAdminAreas: jest.fn(),
            updateAdminAreaOrThrow: jest.fn(),
          },
        },
      ],
    }).compile();

    service = module.get(AdminAreasService);
    repository = module.get(AdminAreasRepository);
  });

  describe('getAdminAreas', () => {
    it('should forward all query params to the repository', async () => {
      const query = {
        filter: "countryCodeIso3='ETH' AND adminLevel=1",
        limit: '500',
      };

      await service.getAdminAreas(query);

      expect(repository.getAdminAreas).toHaveBeenCalledWith(query);
    });
  });

  describe('createAdminAreas', () => {
    it('should create no admin areas when one geometry is not in EPSG:4326', async () => {
      // Arrange
      const adminAreas = [
        validAdminArea,
        { ...validAdminArea, placeCode: 'TEST02', geometry: geometryInMetres },
      ];

      // Act
      const act = service.createAdminAreas(adminAreas);

      // Assert
      await expect(act).rejects.toThrow(
        new BadRequestException(
          "Invalid geometry for admin area 'TEST02': position [3784863,-1574216] is not in the EPSG:4326 range (longitude -180 to 180, latitude -90 to 90)",
        ),
      );
      expect(repository.createAdminAreas).not.toHaveBeenCalled();
    });
  });

  describe('updateAdminAreaOrThrow', () => {
    it('should reject a geometry that is not in EPSG:4326', async () => {
      // Arrange
      const adminAreaUpdateDto = { geometry: geometryInMetres };

      // Act
      const act = service.updateAdminAreaOrThrow({
        placeCode: 'TEST01',
        adminAreaUpdateDto,
      });

      // Assert
      await expect(act).rejects.toThrow(BadRequestException);
      expect(repository.updateAdminAreaOrThrow).not.toHaveBeenCalled();
    });
  });
});
