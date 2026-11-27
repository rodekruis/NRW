import { OmitType } from '@nestjs/swagger';

import { AlertConfigResponseDto } from '@api-service/src/alert-configs/dto/alert-config-response.dto';

export class AlertConfigWithoutGeometryDto extends OmitType(
  AlertConfigResponseDto,
  ['spatialExtentGeometry'] as const,
) {}
