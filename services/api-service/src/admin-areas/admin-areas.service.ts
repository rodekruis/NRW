import { BadRequestException, Injectable } from '@nestjs/common';
import type { Feature, FeatureCollection } from 'geojson';

import { AdminAreasRepository } from '@api-service/src/admin-areas/admin-areas.repository';
import { AdminAreaCreateDto } from '@api-service/src/admin-areas/dto/admin-area-create.dto';
import { AdminAreaUpdateDto } from '@api-service/src/admin-areas/dto/admin-area-update.dto';
import { getWgs84GeometryError } from '@api-service/src/utils/wgs84.helper';

@Injectable()
export class AdminAreasService {
  public constructor(
    private readonly adminAreasRepository: AdminAreasRepository,
  ) {}

  public async getAdminAreas(
    query: Record<string, string>,
  ): Promise<FeatureCollection> {
    return this.adminAreasRepository.getAdminAreas(query);
  }

  public async createAdminAreas(dtos: AdminAreaCreateDto[]): Promise<void> {
    // Check all geometries first: the repository inserts in batches without a transaction
    for (const dto of dtos) {
      this.validateGeometryOrThrow({
        geometry: dto.geometry,
        placeCode: dto.placeCode,
      });
    }
    return this.adminAreasRepository.createAdminAreas(dtos);
  }

  public async updateAdminAreaOrThrow({
    placeCode,
    adminAreaUpdateDto,
  }: {
    placeCode: string;
    adminAreaUpdateDto: AdminAreaUpdateDto;
  }): Promise<Feature> {
    if (adminAreaUpdateDto.geometry !== undefined) {
      this.validateGeometryOrThrow({
        geometry: adminAreaUpdateDto.geometry,
        placeCode,
      });
    }
    return this.adminAreasRepository.updateAdminAreaOrThrow({
      placeCode,
      adminAreaUpdateDto,
    });
  }

  public async deleteAdminAreaOrThrow(placeCode: string): Promise<void> {
    return this.adminAreasRepository.deleteAdminAreaOrThrow(placeCode);
  }

  private validateGeometryOrThrow({
    geometry,
    placeCode,
  }: {
    geometry: Record<string, unknown>;
    placeCode: string;
  }): void {
    const error = getWgs84GeometryError(geometry);
    if (error) {
      throw new BadRequestException(
        `Invalid geometry for admin area '${placeCode}': ${error}`,
      );
    }
  }
}
