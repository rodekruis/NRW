import { BadRequestException, Injectable } from '@nestjs/common';
import type { Feature, FeatureCollection } from 'geojson';

import { GeoFeatureCreateDto } from '@api-service/src/geo-features/dto/geo-feature-create.dto';
import { GeoFeatureUpdateDto } from '@api-service/src/geo-features/dto/geo-feature-update.dto';
import { GeoFeaturesRepository } from '@api-service/src/geo-features/geo-features.repository';
import { getWgs84GeometryError } from '@api-service/src/utils/wgs84.helper';

@Injectable()
export class GeoFeaturesService {
  public constructor(
    private readonly geoFeaturesRepository: GeoFeaturesRepository,
  ) {}

  public async getGeoFeatures(
    query: Record<string, string>,
  ): Promise<FeatureCollection> {
    return this.geoFeaturesRepository.getGeoFeatures(query);
  }

  public async createGeoFeatures(dtos: GeoFeatureCreateDto[]): Promise<void> {
    // Check all geometries first: the repository inserts in batches without a transaction
    for (const dto of dtos) {
      this.validateGeometryOrThrow({
        geometry: dto.geometry,
        name: `'${dto.referenceId}'`,
      });
    }
    return this.geoFeaturesRepository.createGeoFeatures(dtos);
  }

  public async updateGeoFeatureOrThrow({
    id,
    geoFeatureUpdateDto,
  }: {
    id: number;
    geoFeatureUpdateDto: GeoFeatureUpdateDto;
  }): Promise<Feature> {
    if (geoFeatureUpdateDto.geometry !== undefined) {
      this.validateGeometryOrThrow({
        geometry: geoFeatureUpdateDto.geometry,
        name: `with id ${id}`,
      });
    }
    return this.geoFeaturesRepository.updateGeoFeatureOrThrow({
      id,
      geoFeatureUpdateDto,
    });
  }

  public async deleteGeoFeatureOrThrow(id: number): Promise<void> {
    return this.geoFeaturesRepository.deleteGeoFeatureOrThrow(id);
  }

  private validateGeometryOrThrow({
    geometry,
    name,
  }: {
    geometry: Record<string, unknown>;
    name: string;
  }): void {
    const error = getWgs84GeometryError(geometry);
    if (error) {
      throw new BadRequestException(
        `Invalid geometry for geo-feature ${name}: ${error}`,
      );
    }
  }
}
