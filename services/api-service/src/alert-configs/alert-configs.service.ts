import { BadRequestException, Injectable } from '@nestjs/common';

import { AlertConfigsRepository } from '@api-service/src/alert-configs/alert-configs.repository';
import { AlertConfigCreateDto } from '@api-service/src/alert-configs/dto/alert-config-create.dto';
import { AlertConfigResponseDto } from '@api-service/src/alert-configs/dto/alert-config-response.dto';
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

  public async createAlertConfigs(
    dtos: AlertConfigCreateDto[],
  ): Promise<AlertConfigResponseDto[]> {
    for (const dto of dtos) {
      this.validateSpatialExtentGeometryOrThrow(dto);
    }
    return this.alertConfigsRepository.createAlertConfigs(dtos);
  }

  private validateSpatialExtentGeometryOrThrow({
    spatialExtentGeometry,
    spatialExtentName,
  }: AlertConfigCreateDto): void {
    if (spatialExtentGeometry === undefined || spatialExtentGeometry === null) {
      return;
    }
    const error = getPolygonGeometryError(spatialExtentGeometry);
    if (error) {
      throw new BadRequestException(
        `Invalid spatialExtentGeometry for alert config '${spatialExtentName}': ${error}`,
      );
    }
  }

  public async deleteAlertConfigOrThrow(id: number): Promise<void> {
    await this.alertConfigsRepository.deleteAlertConfigOrThrow(id);
  }
}
