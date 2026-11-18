import { ApiProperty } from '@nestjs/swagger';
import { Type } from 'class-transformer';
import { IsIn, IsNumber, ValidateNested } from 'class-validator';

import { RasterExtentDto } from '@api-service/src/alerts/dto/raster-extent.dto';
import { EPSG } from '@api-service/src/shared/enum/epsg.enum';

class RasterDataMetadata {
  @ApiProperty({ type: RasterExtentDto })
  @ValidateNested()
  @Type(() => RasterExtentDto)
  public readonly extent: RasterExtentDto;

  @ApiProperty({
    enum: [EPSG.WGS84],
    example: EPSG.WGS84,
    description: 'CRS of the extent and of the raster data',
  })
  @IsIn([EPSG.WGS84])
  public readonly crs: EPSG.WGS84;

  @ApiProperty({ example: 0 })
  @IsNumber()
  public readonly nodata: number;
}

class RasterColouredMetadata {
  @ApiProperty({ type: RasterExtentDto })
  @ValidateNested()
  @Type(() => RasterExtentDto)
  public readonly extent: RasterExtentDto;

  @ApiProperty({
    enum: [EPSG.WebMercator],
    example: EPSG.WebMercator,
    description: 'CRS of the extent and of the rows of the coloured image',
  })
  @IsIn([EPSG.WebMercator])
  public readonly crs: EPSG.WebMercator;
}

export class RasterMetadataDto {
  @ApiProperty({ type: RasterDataMetadata })
  @ValidateNested()
  @Type(() => RasterDataMetadata)
  public readonly data: RasterDataMetadata;

  @ApiProperty({ type: RasterColouredMetadata })
  @ValidateNested()
  @Type(() => RasterColouredMetadata)
  public readonly coloured: RasterColouredMetadata;
}
