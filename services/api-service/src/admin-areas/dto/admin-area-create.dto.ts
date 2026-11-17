import { ApiProperty, ApiPropertyOptional } from '@nestjs/swagger';
import { IsInt, IsObject, IsOptional, IsString } from 'class-validator';

export class AdminAreaCreateDto {
  @ApiProperty({ example: 'KEN.10_1' })
  @IsString()
  public readonly placeCode: string;

  @ApiProperty({ example: 1 })
  @IsInt()
  public readonly adminLevel: number;

  @ApiProperty({ example: 'Nairobi' })
  @IsString()
  public readonly nameEn: string;

  @ApiProperty({ example: 'KEN' })
  @IsString()
  public readonly countryCodeIso3: string;

  @ApiProperty({ example: 'KE', type: String })
  @IsString()
  public readonly placeCodeLevel0: string;

  @ApiPropertyOptional({ example: 'KEN.10_1', nullable: true })
  @IsOptional()
  @IsString()
  public readonly placeCodeLevel1?: string | null;

  @ApiPropertyOptional({ example: 'KEN.10.1_1', nullable: true })
  @IsOptional()
  @IsString()
  public readonly placeCodeLevel2?: string | null;

  @ApiPropertyOptional({ example: 'KEN.10.1.1_1', nullable: true })
  @IsOptional()
  @IsString()
  public readonly placeCodeLevel3?: string | null;

  @ApiPropertyOptional({ example: 'KEN.10.1.1.1_1', nullable: true })
  @IsOptional()
  @IsString()
  public readonly placeCodeLevel4?: string | null;

  @ApiPropertyOptional({
    example: { POPULATION: 215293 },
  })
  @IsOptional()
  @IsObject()
  public readonly attributes?: Record<string, unknown>;

  @ApiProperty({
    description:
      "GeoJSON MultiPolygon geometry in EPSG:4326, as [longitude, latitude], without a 'crs' member",
    example: {
      type: 'MultiPolygon',
      coordinates: [
        [
          [
            [36.7, -1.4],
            [37.1, -1.4],
            [37.1, -1.2],
            [36.7, -1.4],
          ],
        ],
      ],
    },
  })
  @IsObject()
  public readonly geometry: Record<string, unknown>;
}
