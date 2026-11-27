import {
  BadRequestException,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { Prisma } from '@prisma/client';
import type { MultiPolygon, Polygon } from 'geojson';

import { AlertConfigCreateDto } from '@api-service/src/alert-configs/dto/alert-config-create.dto';
import { AlertConfigResponseDto } from '@api-service/src/alert-configs/dto/alert-config-response.dto';
import { AlertConfigUpdateDto } from '@api-service/src/alert-configs/dto/alert-config-update.dto';
import { AlertConfigWithoutGeometryDto } from '@api-service/src/alert-configs/dto/alert-config-without-geometry.dto';
import { ClassLevelDto } from '@api-service/src/alert-configs/dto/class-level.dto';
import { PrismaService } from '@api-service/src/prisma/prisma.service';
import { HazardType } from '@api-service/src/shared-enums';

type AlertConfigRow = Prisma.AlertConfigGetPayload<null>;

const omitSpatialExtentGeometry = {
  spatialExtentGeometry: true,
} as const satisfies Prisma.AlertConfigOmit;

type AlertConfigWithoutGeometryRow = Prisma.AlertConfigGetPayload<{
  omit: typeof omitSpatialExtentGeometry;
}>;

@Injectable()
export class AlertConfigsRepository {
  public constructor(private readonly prisma: PrismaService) {}

  private toResponseDto(row: AlertConfigRow): AlertConfigResponseDto {
    return {
      ...this.toWithoutGeometryDto(row),
      spatialExtentGeometry: row.spatialExtentGeometry as unknown as
        Polygon | MultiPolygon | null,
    };
  }

  private toWithoutGeometryDto(
    row: AlertConfigWithoutGeometryRow,
  ): AlertConfigWithoutGeometryDto {
    return {
      id: row.id,
      created: row.created,
      updated: row.updated,
      countryCodeIso3: row.countryCodeIso3,
      hazardType: row.hazardType,
      spatialExtentName: row.spatialExtentName,
      temporalExtents: row.temporalExtents as unknown as Record<
        string,
        string[] | number[]
      >[],
      severityClassLevels:
        row.severityClassLevels as unknown as ClassLevelDto[],
      probabilityClassLevels:
        row.probabilityClassLevels as unknown as ClassLevelDto[],
      triggerAlertClass: row.triggerAlertClass,
      triggerLeadTimeDuration: row.triggerLeadTimeDuration,
    };
  }

  public async getAlertConfigs({
    countryCodeIso3,
    hazardType,
  }: {
    countryCodeIso3?: string;
    hazardType?: HazardType;
  }): Promise<AlertConfigResponseDto[]> {
    const rows = await this.prisma.alertConfig.findMany({
      where: this.getAlertConfigsWhere({ countryCodeIso3, hazardType }),
      orderBy: { updated: 'desc' },
    });
    return rows.map((row: AlertConfigRow) => this.toResponseDto(row));
  }

  public async getAlertConfigsWithoutGeometry({
    countryCodeIso3,
    hazardType,
  }: {
    countryCodeIso3: string;
    hazardType: HazardType;
  }): Promise<AlertConfigWithoutGeometryDto[]> {
    const rows = await this.prisma.alertConfig.findMany({
      where: this.getAlertConfigsWhere({ countryCodeIso3, hazardType }),
      omit: omitSpatialExtentGeometry,
      orderBy: { updated: 'desc' },
    });
    return rows.map((row: AlertConfigWithoutGeometryRow) =>
      this.toWithoutGeometryDto(row),
    );
  }

  private getAlertConfigsWhere({
    countryCodeIso3,
    hazardType,
  }: {
    countryCodeIso3?: string;
    hazardType?: HazardType;
  }): Prisma.AlertConfigWhereInput {
    return {
      ...(countryCodeIso3 !== undefined && { countryCodeIso3 }),
      ...(hazardType !== undefined && { hazardType }),
    };
  }

  public async updateAlertConfigOrThrow({
    id,
    alertConfigUpdateDto,
  }: {
    id: number;
    alertConfigUpdateDto: AlertConfigUpdateDto;
  }): Promise<AlertConfigResponseDto> {
    try {
      const row = await this.prisma.alertConfig.update({
        where: { id },
        data: this.toUpdateInput(alertConfigUpdateDto),
      });
      return this.toResponseDto(row);
    } catch (error) {
      if (error instanceof Prisma.PrismaClientKnownRequestError) {
        if (error.code === 'P2025') {
          throw new NotFoundException(`Alert config with id ${id} not found`);
        }
      }
      throw error;
    }
  }

  public async deleteAlertConfigOrThrow(id: number): Promise<void> {
    const row = await this.prisma.alertConfig.findUnique({ where: { id } });
    if (!row) {
      throw new NotFoundException(`Alert config with id ${id} not found`);
    }
    await this.prisma.alertConfig.delete({ where: { id } });
  }

  public async createAlertConfigs(
    dtos: AlertConfigCreateDto[],
  ): Promise<AlertConfigResponseDto[]> {
    if (dtos.length === 0) {
      return [];
    }

    try {
      const rows = await this.prisma.$transaction(
        dtos.map((dto) =>
          this.prisma.alertConfig.create({
            data: {
              countryCodeIso3: dto.countryCodeIso3,
              hazardType: dto.hazardType,
              spatialExtentName: dto.spatialExtentName,
              spatialExtentGeometry: this.toSpatialExtentGeometryInput(
                dto.spatialExtentGeometry,
              ),
              temporalExtents:
                dto.temporalExtents as unknown as Prisma.InputJsonValue,
              severityClassLevels:
                dto.severityClassLevels as unknown as Prisma.InputJsonValue,
              probabilityClassLevels:
                dto.probabilityClassLevels as unknown as Prisma.InputJsonValue,
              triggerAlertClass: dto.triggerAlertClass ?? null,
              triggerLeadTimeDuration: dto.triggerLeadTimeDuration ?? null,
            },
          }),
        ),
      );
      return rows.map((row) => this.toResponseDto(row));
    } catch (error) {
      if (error instanceof Prisma.PrismaClientKnownRequestError) {
        if (error.code === 'P2003') {
          throw new BadRequestException(
            'One or more referenced countries do not exist',
          );
        }
      }
      throw error;
    }
  }

  // Only the properties in the body change; null clears a nullable property
  private toUpdateInput(
    alertConfigUpdateDto: AlertConfigUpdateDto,
  ): Prisma.AlertConfigUpdateInput {
    const {
      spatialExtentGeometry,
      temporalExtents,
      severityClassLevels,
      probabilityClassLevels,
      triggerAlertClass,
      triggerLeadTimeDuration,
    } = alertConfigUpdateDto;
    return {
      ...(spatialExtentGeometry !== undefined && {
        spatialExtentGeometry: this.toSpatialExtentGeometryInput(
          spatialExtentGeometry,
        ),
      }),
      ...(temporalExtents !== undefined && {
        temporalExtents: temporalExtents as unknown as Prisma.InputJsonValue,
      }),
      ...(severityClassLevels !== undefined && {
        severityClassLevels:
          severityClassLevels as unknown as Prisma.InputJsonValue,
      }),
      ...(probabilityClassLevels !== undefined && {
        probabilityClassLevels:
          probabilityClassLevels as unknown as Prisma.InputJsonValue,
      }),
      ...(triggerAlertClass !== undefined && { triggerAlertClass }),
      ...(triggerLeadTimeDuration !== undefined && { triggerLeadTimeDuration }),
    };
  }

  // Why PostGIS considers the geometry invalid, for example 'Self-intersection[34.25 -13.75]';
  // undefined when it is valid
  public async getGeometryTopologyError(
    geometry: Polygon | MultiPolygon,
  ): Promise<string | undefined> {
    const geojson = JSON.stringify(geometry);
    const [result] = await this.prisma.$queryRaw<
      { invalidReason: string | null }[]
    >`
      SELECT CASE WHEN public.ST_IsValid(geometry) THEN NULL
        ELSE public.ST_IsValidReason(geometry) END AS "invalidReason"
      FROM (SELECT public.ST_GeomFromGeoJSON(${geojson}) AS geometry) AS input`;
    return result?.invalidReason ?? undefined;
  }

  private toSpatialExtentGeometryInput(
    spatialExtentGeometry: Polygon | MultiPolygon | null | undefined,
  ): Prisma.InputJsonValue | Prisma.NullTypes.DbNull {
    return spatialExtentGeometry
      ? (spatialExtentGeometry as unknown as Prisma.InputJsonValue)
      : Prisma.DbNull;
  }
}
