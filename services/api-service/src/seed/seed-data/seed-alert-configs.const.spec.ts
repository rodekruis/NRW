import seedAlertConfigSpatialExtents from '@api-service/src/seed/seed-data/seed-alert-config-spatial-extents.json';
import {
  SEED_COMPOUND_FLOODS_ALERT_CONFIGS,
  SEED_DROUGHT_ALERT_CONFIGS,
  SeedAlertConfig,
} from '@api-service/src/seed/seed-data/seed-alert-configs.const';

const NATIONAL_SPATIAL_EXTENT_NAME = 'National';

const alertConfigsWithSpatialExtent: SeedAlertConfig[] = [
  ...SEED_COMPOUND_FLOODS_ALERT_CONFIGS,
  ...SEED_DROUGHT_ALERT_CONFIGS.filter(
    (config) => config.spatialExtentName !== NATIONAL_SPATIAL_EXTENT_NAME,
  ),
];

describe('Seed alert configs', () => {
  it.each(
    alertConfigsWithSpatialExtent.map((config) => ({
      config,
      label: `${config.countryCodeIso3} ${config.hazardType} ${config.spatialExtentName}`,
    })),
  )(
    'should give $label the geometry of its feature in the spatial extents file',
    ({ config }) => {
      // Arrange
      const { features } = seedAlertConfigSpatialExtents;

      // Act
      const feature = features.find(
        ({ properties }) =>
          properties.hazardType === config.hazardType &&
          properties.countryCodeIso3 === config.countryCodeIso3 &&
          properties.spatialExtentName === config.spatialExtentName,
      );

      // Assert
      expect(feature).toBeDefined();
      expect(config.spatialExtentGeometry).toEqual(feature?.geometry);
    },
  );

  it("should give 'National' drought configs no geometry", () => {
    // Arrange
    const nationalDroughtConfigs = SEED_DROUGHT_ALERT_CONFIGS.filter(
      (config) => config.spatialExtentName === NATIONAL_SPATIAL_EXTENT_NAME,
    );

    // Act
    const geometries = nationalDroughtConfigs.map(
      (config) => config.spatialExtentGeometry,
    );

    // Assert
    expect(geometries.length).toBeGreaterThan(0);
    expect(geometries.every((geometry) => geometry === null)).toBe(true);
  });
});
