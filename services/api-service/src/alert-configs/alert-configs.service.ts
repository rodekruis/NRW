import { BadRequestException, Injectable } from '@nestjs/common';
import type { MultiPolygon, Polygon } from 'geojson';

import { AlertConfigsRepository } from '@api-service/src/alert-configs/alert-configs.repository';
import { AlertConfigCreateDto } from '@api-service/src/alert-configs/dto/alert-config-create.dto';
import { AlertConfigResponseDto } from '@api-service/src/alert-configs/dto/alert-config-response.dto';
import { AlertConfigUpdateDto } from '@api-service/src/alert-configs/dto/alert-config-update.dto';
import { AlertConfigWithoutGeometryDto } from '@api-service/src/alert-configs/dto/alert-config-without-geometry.dto';
import { HazardType } from '@api-service/src/shared-enums';
import { getPolygonGeometryError } from '@api-service/src/utils/polygon-geometry.helper';

@Injectable()
export class AlertConfigsService {
  public constructor(
    private readonly alertConfigsRepository: AlertConfigsRepository,
  ) {}

  public async getAlertConfigs({
    countryCodeIso3,
    hazardType,
  }: {
    countryCodeIso3?: string;
    hazardType?: HazardType;
  }): Promise<AlertConfigResponseDto[]> {
    return this.alertConfigsRepository.getAlertConfigs({
      countryCodeIso3,
      hazardType,
    });
  }

  public async getAlertConfigsWithoutGeometry({
    countryCodeIso3,
    hazardType,
  }: {
    countryCodeIso3: string;
    hazardType: HazardType;
  }): Promise<AlertConfigWithoutGeometryDto[]> {
    return this.alertConfigsRepository.getAlertConfigsWithoutGeometry({
      countryCodeIso3,
      hazardType,
    });
  }

  public async createAlertConfigs(
    dtos: AlertConfigCreateDto[],
  ): Promise<AlertConfigResponseDto[]> {
    for (const { spatialExtentGeometry, spatialExtentName } of dtos) {
      await this.validateSpatialExtentGeometryOrThrow({
        spatialExtentGeometry,
        name: `'${spatialExtentName}'`,
      });
    }
    return this.alertConfigsRepository.createAlertConfigs(dtos);
  }

  public async updateAlertConfigOrThrow({
    id,
    alertConfigUpdateDto,
  }: {
    id: number;
    alertConfigUpdateDto: AlertConfigUpdateDto;
  }): Promise<AlertConfigResponseDto> {
    await this.validateSpatialExtentGeometryOrThrow({
      spatialExtentGeometry: alertConfigUpdateDto.spatialExtentGeometry,
      name: `with id ${id}`,
    });
    return this.alertConfigsRepository.updateAlertConfigOrThrow({
      id,
      alertConfigUpdateDto,
    });
  }

  private async validateSpatialExtentGeometryOrThrow({
    spatialExtentGeometry,
    name,
  }: {
    spatialExtentGeometry: Polygon | MultiPolygon | null | undefined;
    name: string;
  }): Promise<void> {
    if (spatialExtentGeometry === undefined || spatialExtentGeometry === null) {
      return;
    }
    // The topology check (self-intersections, holes outside their shell) needs PostGIS,
    // so it only runs when the structure is fine
    const error =
      getPolygonGeometryError(spatialExtentGeometry) ??
      (await this.alertConfigsRepository.getGeometryTopologyError(
        spatialExtentGeometry,
      ));
    if (error) {
      throw new BadRequestException(
        `Invalid spatialExtentGeometry for alert config ${name}: ${error}`,
      );
    }
  }

  public async deleteAlertConfigOrThrow(id: number): Promise<void> {
    await this.alertConfigsRepository.deleteAlertConfigOrThrow(id);
  }
}
