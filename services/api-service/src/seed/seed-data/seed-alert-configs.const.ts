import type { MultiPolygon, Polygon } from 'geojson';

import seedAlertConfigSpatialExtents from '@api-service/src/seed/seed-data/seed-alert-config-spatial-extents.json';
import {
  AlertClass,
  AlertClassificationLevel,
  HazardType,
} from '@api-service/src/shared-enums';

interface ClassLevel {
  readonly label: AlertClassificationLevel;
  readonly threshold: number;
}

export interface SeedAlertConfig {
  readonly countryCodeIso3: string;
  readonly hazardType: HazardType;
  readonly spatialExtentName: string;
  readonly spatialExtentGeometry: Polygon | MultiPolygon | null;
  readonly temporalExtents: Record<string, string[] | number[]>[];
  readonly severityClassLevels: ClassLevel[];
  readonly probabilityClassLevels: ClassLevel[];
  readonly triggerAlertClass: AlertClass | null;
  readonly triggerLeadTimeDuration: string | null;
}

interface SeedAlertConfigSpatialExtentFeature {
  readonly properties: {
    readonly hazardType: HazardType;
    readonly countryCodeIso3: string;
    readonly spatialExtentName: string;
  };
  readonly geometry: Polygon | MultiPolygon;
}

// The drought and compound-flood geometries live in code for now.
// They should probably move to the seed-data repo, like the flood ones.
const SEED_ALERT_CONFIG_SPATIAL_EXTENT_FEATURES = (
  seedAlertConfigSpatialExtents as unknown as {
    readonly features: SeedAlertConfigSpatialExtentFeature[];
  }
).features;

function getSpatialExtentGeometry({
  hazardType,
  countryCodeIso3,
  spatialExtentName,
}: {
  hazardType: HazardType;
  countryCodeIso3: string;
  spatialExtentName: string;
}): Polygon | MultiPolygon | null {
  const feature = SEED_ALERT_CONFIG_SPATIAL_EXTENT_FEATURES.find(
    ({ properties }) =>
      properties.hazardType === hazardType &&
      properties.countryCodeIso3 === countryCodeIso3 &&
      properties.spatialExtentName === spatialExtentName,
  );
  return feature?.geometry ?? null;
}

// --- FLOODS: in-code config ---
// TODO: should some of the below come from a seed-data repo source instead of defined in code?

export const FLOOD_LEAD_TIME_SPECTRUM = [
  '0-day',
  '1-day',
  '2-day',
  '3-day',
  '4-day',
  '5-day',
  '6-day',
  '7-day',
];

interface FloodClassificationConfig {
  readonly severityClassLevels: ClassLevel[];
  readonly probabilityClassLevels: ClassLevel[];
  readonly triggerAlertClass: AlertClass;
  readonly triggerLeadTimeDuration: string;
}

const { singleThreshold, low, medium, high } = AlertClassificationLevel;

// All configs use 'single' for at least one dimension (severity or probability).
// This avoids the non-independence issue between severity and probability
// See ALERT_CLASS_MATRIX for details.
export const FLOOD_CLASSIFICATION_BY_COUNTRY: Record<
  string,
  FloodClassificationConfig
> = {
  UGA: {
    severityClassLevels: [
      { label: low, threshold: 1.5 },
      { label: medium, threshold: 2 },
      { label: high, threshold: 5 },
    ],
    probabilityClassLevels: [{ label: singleThreshold, threshold: 0.6 }],
    triggerAlertClass: AlertClass.high,
    triggerLeadTimeDuration: 'P5D',
  },
  KEN: {
    severityClassLevels: [{ label: singleThreshold, threshold: 5 }],
    probabilityClassLevels: [{ label: singleThreshold, threshold: 0.85 }],
    triggerAlertClass: AlertClass.high,
    triggerLeadTimeDuration: 'P7D',
  },
  ETH: {
    severityClassLevels: [
      { label: low, threshold: 2 },
      { label: medium, threshold: 5 },
      { label: high, threshold: 10 },
    ],
    probabilityClassLevels: [{ label: singleThreshold, threshold: 0.75 }],
    triggerAlertClass: AlertClass.high,
    triggerLeadTimeDuration: 'P7D',
  },
  ZMB: {
    severityClassLevels: [{ label: singleThreshold, threshold: 10 }],
    probabilityClassLevels: [
      { label: low, threshold: 0.6 },
      { label: medium, threshold: 0.7 },
      { label: high, threshold: 0.8 },
    ],
    triggerAlertClass: AlertClass.high,
    triggerLeadTimeDuration: 'P7D',
  },
  SSD: {
    severityClassLevels: [{ label: singleThreshold, threshold: 5 }],
    probabilityClassLevels: [{ label: singleThreshold, threshold: 0.6 }],
    triggerAlertClass: AlertClass.high,
    triggerLeadTimeDuration: 'P7D',
  },
  MWI: {
    severityClassLevels: [{ label: singleThreshold, threshold: 5 }],
    probabilityClassLevels: [{ label: singleThreshold, threshold: 0.6 }],
    triggerAlertClass: AlertClass.high,
    triggerLeadTimeDuration: 'P6D',
  },
  PHL: {
    severityClassLevels: [{ label: singleThreshold, threshold: 5 }],
    probabilityClassLevels: [{ label: singleThreshold, threshold: 0.8 }],
    triggerAlertClass: AlertClass.high,
    triggerLeadTimeDuration: 'P3D',
  },
};

// --- DROUGHT: in-code config ---
// TODO: should some of the below come from a seed-data repo source instead of defined in code?

const DROUGHT_SEVERITY_CLASS_LEVELS: ClassLevel[] = [
  { label: singleThreshold, threshold: 0.2 },
];

const DROUGHT_PROBABILITY_CLASS_LEVELS: ClassLevel[] = [
  { label: singleThreshold, threshold: 0 },
];

function createDroughtAlertConfig({
  countryCodeIso3,
  regionName,
  seasons,
}: {
  countryCodeIso3: string;
  regionName: string;
  seasons: Record<string, number[]>[];
}): SeedAlertConfig {
  return {
    countryCodeIso3,
    hazardType: HazardType.drought,
    spatialExtentName: regionName,
    spatialExtentGeometry: getSpatialExtentGeometry({
      hazardType: HazardType.drought,
      countryCodeIso3,
      spatialExtentName: regionName,
    }),
    temporalExtents: seasons,
    severityClassLevels: DROUGHT_SEVERITY_CLASS_LEVELS,
    probabilityClassLevels: DROUGHT_PROBABILITY_CLASS_LEVELS,
    triggerAlertClass: null,
    triggerLeadTimeDuration: null,
  };
}

// --- DROUGHT: ETH  ---

// The climate regions of ETH and UGA are geometries in seed-alert-config-spatial-extents.json.
// The pipeline derives their admin areas from these geometries. 'National' regions have no geometry.

const ETH_DROUGHT_CONFIGS: SeedAlertConfig[] = [
  createDroughtAlertConfig({
    countryCodeIso3: 'ETH',
    regionName: 'Belg',
    seasons: [{ MAM: [2, 3, 4, 5] }, { JAS: [6, 7, 8, 9] }],
  }),
  createDroughtAlertConfig({
    countryCodeIso3: 'ETH',
    regionName: 'Meher',
    seasons: [{ JAS: [6, 7, 8, 9] }],
  }),
  createDroughtAlertConfig({
    countryCodeIso3: 'ETH',
    regionName: 'Northern',
    seasons: [{ MAM: [3, 4, 5] }, { JAS: [7, 8, 9] }],
  }),
  createDroughtAlertConfig({
    countryCodeIso3: 'ETH',
    regionName: 'Southern',
    seasons: [{ MAM: [3, 4, 5] }, { OND: [10, 11, 12] }],
  }),
];

// --- DROUGHT: KEN ---

const KEN_DROUGHT_CONFIGS: SeedAlertConfig[] = [
  createDroughtAlertConfig({
    countryCodeIso3: 'KEN',
    regionName: 'National',
    seasons: [{ MAM: [3, 4, 5] }, { OND: [10, 11, 12] }],
  }),
];

// --- DROUGHT: UGA ---

const UGA_DROUGHT_CONFIGS: SeedAlertConfig[] = [
  createDroughtAlertConfig({
    countryCodeIso3: 'UGA',
    regionName: 'Karamoja',
    seasons: [{ Karamoja: [4, 5, 6, 7, 8, 9, 10] }],
  }),
  createDroughtAlertConfig({
    countryCodeIso3: 'UGA',
    regionName: 'Central',
    seasons: [{ MAM: [3, 4, 5] }, { OND: [9, 10, 11] }],
  }),
];

// --- DROUGHT: ZMB ---

const ZMB_DROUGHT_CONFIGS: SeedAlertConfig[] = [
  createDroughtAlertConfig({
    countryCodeIso3: 'ZMB',
    regionName: 'National',
    seasons: [{ OND: [10, 11, 12, 1, 2, 3] }],
  }),
];

// --- DROUGHT: ZWE ---

const ZWE_DROUGHT_CONFIGS: SeedAlertConfig[] = [
  createDroughtAlertConfig({
    countryCodeIso3: 'ZWE',
    regionName: 'National',
    seasons: [{ MAM: [4, 5, 6, 7, 8] }],
  }),
];

// --- DROUGHT: LSO ---

const LSO_DROUGHT_CONFIGS: SeedAlertConfig[] = [
  createDroughtAlertConfig({
    countryCodeIso3: 'LSO',
    regionName: 'National',
    seasons: [{ Drought: [10, 11, 12, 1, 2, 3] }],
  }),
];

export const SEED_DROUGHT_ALERT_CONFIGS: SeedAlertConfig[] = [
  ...ETH_DROUGHT_CONFIGS,
  ...KEN_DROUGHT_CONFIGS,
  ...UGA_DROUGHT_CONFIGS,
  ...ZMB_DROUGHT_CONFIGS,
  ...ZWE_DROUGHT_CONFIGS,
  ...LSO_DROUGHT_CONFIGS,
];

// --- TROPICAL CYCLONE: in-code config ---

const TROPICAL_CYCLONE_LEAD_TIME_STEP_HOURS = 3;
const TROPICAL_CYCLONE_LEAD_TIME_MAX_HOURS = 168;

const TROPICAL_CYCLONE_LEAD_TIME_SPECTRUM = Array.from(
  {
    length:
      TROPICAL_CYCLONE_LEAD_TIME_MAX_HOURS /
        TROPICAL_CYCLONE_LEAD_TIME_STEP_HOURS +
      1,
  },
  (_, i) => `${i * TROPICAL_CYCLONE_LEAD_TIME_STEP_HOURS}-hour`,
);

interface TropicalCycloneClassificationConfig {
  readonly severityClassLevels: ClassLevel[];
  readonly probabilityClassLevels: ClassLevel[];
  readonly triggerAlertClass: AlertClass | null;
  readonly triggerLeadTimeDuration: string | null;
}

const TROPICAL_CYCLONE_CLASSIFICATION_BY_COUNTRY: Record<
  string,
  TropicalCycloneClassificationConfig
> = {
  PHL: {
    severityClassLevels: [
      { label: low, threshold: 33 },
      { label: high, threshold: 43 },
    ],
    probabilityClassLevels: [{ label: singleThreshold, threshold: 0 }],
    triggerAlertClass: AlertClass.high,
    triggerLeadTimeDuration: 'P3D',
  },
};

export const SEED_TROPICAL_CYCLONE_ALERT_CONFIGS: SeedAlertConfig[] =
  Object.entries(TROPICAL_CYCLONE_CLASSIFICATION_BY_COUNTRY).map(
    ([countryCodeIso3, config]) => ({
      countryCodeIso3,
      hazardType: HazardType.tropicalCyclone,
      spatialExtentName: 'National',
      spatialExtentGeometry: null,
      temporalExtents: [
        { 'lead-time-spectrum': TROPICAL_CYCLONE_LEAD_TIME_SPECTRUM },
      ],
      severityClassLevels: config.severityClassLevels,
      probabilityClassLevels: config.probabilityClassLevels,
      triggerAlertClass: config.triggerAlertClass,
      triggerLeadTimeDuration: config.triggerLeadTimeDuration,
    }),
  );

// --- COMPOUND FLOODS: in-code config ---
// TODO: should some of the below come from a seed-data repo source instead of defined in code?

const COMPOUND_FLOODS_LEAD_TIME_SPECTRUM = [
  '0-day',
  '1-day',
  '2-day',
  '3-day',
  '4-day',
  '5-day',
];

interface CompoundFloodClassificationConfig {
  readonly severityClassLevels: ClassLevel[];
  readonly probabilityClassLevels: ClassLevel[];
  readonly triggerAlertClass: AlertClass | null;
  readonly triggerLeadTimeDuration: string | null;
}

const COMPOUND_FLOODS_CLASSIFICATION_BY_COUNTRY: Record<
  string,
  CompoundFloodClassificationConfig
> = {
  PHL: {
    severityClassLevels: [
      { label: low, threshold: 1.5 },
      { label: medium, threshold: 2 },
      { label: high, threshold: 5 },
    ],
    probabilityClassLevels: [{ label: singleThreshold, threshold: 0 }],
    triggerAlertClass: AlertClass.high,
    triggerLeadTimeDuration: null,
  },
};

// The areas are geometries in seed-alert-config-spatial-extents.json
const COMPOUND_FLOODS_AREA_NAMES_BY_COUNTRY: Record<string, string[]> = {
  PHL: ['Pasig River', 'Santa Maria River', 'Bicol River', 'Panay River'],
};

export const SEED_COMPOUND_FLOODS_ALERT_CONFIGS: SeedAlertConfig[] =
  Object.entries(COMPOUND_FLOODS_CLASSIFICATION_BY_COUNTRY).flatMap(
    ([countryCodeIso3, config]) =>
      (COMPOUND_FLOODS_AREA_NAMES_BY_COUNTRY[countryCodeIso3] ?? []).map(
        (spatialExtentName): SeedAlertConfig => ({
          countryCodeIso3,
          hazardType: HazardType.compoundFloods,
          spatialExtentName,
          spatialExtentGeometry: getSpatialExtentGeometry({
            hazardType: HazardType.compoundFloods,
            countryCodeIso3,
            spatialExtentName,
          }),
          temporalExtents: [
            { 'lead-time-spectrum': COMPOUND_FLOODS_LEAD_TIME_SPECTRUM },
          ],
          severityClassLevels: config.severityClassLevels,
          probabilityClassLevels: config.probabilityClassLevels,
          triggerAlertClass: config.triggerAlertClass,
          triggerLeadTimeDuration: config.triggerLeadTimeDuration,
        }),
      ),
  );
