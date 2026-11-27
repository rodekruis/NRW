import { OmitType, PartialType } from '@nestjs/swagger';

import { AlertConfigCreateDto } from '@api-service/src/alert-configs/dto/alert-config-create.dto';

export class AlertConfigUpdateDto extends PartialType(
  OmitType(AlertConfigCreateDto, [
    'countryCodeIso3',
    'hazardType',
    'spatialExtentName',
  ] as const),
) {}
