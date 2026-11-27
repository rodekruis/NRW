import { ApiProperty } from '@nestjs/swagger';
import type { Position } from 'geojson';

import { POLYGON_GEOMETRY_TYPES } from '@api-service/src/utils/polygon-geometry.helper';

// Describes the geometry for Swagger; AlertConfigsService validates it
export class SpatialExtentGeometryDto {
  @ApiProperty({ enum: POLYGON_GEOMETRY_TYPES, example: 'Polygon' })
  public readonly type: (typeof POLYGON_GEOMETRY_TYPES)[number];

  @ApiProperty({
    description:
      'Coordinates array in EPSG:4326, as [longitude, latitude]; structure depends on geometry type.',
    example: [
      [
        [34.0, -14.0],
        [34.5, -14.0],
        [34.5, -13.5],
        [34.0, -14.0],
      ],
    ],
    type: 'array',
    items: { type: 'array', items: {} },
  })
  public readonly coordinates: Position[][] | Position[][][];
}
