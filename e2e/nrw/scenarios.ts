import { HazardType, MockScenario } from '@nrw-e2e/nrw/helpers/enums';

/**
 * Named database states, each defined once.
 *
 * The mock data doubles as demo data, so it changes over time. Expected
 * values that specs assert on live here, so a mock-data change means
 * updating this file only.
 */
export type Scenario = {
  countryCodes: string[];
  mockScenario: MockScenario;
  hazardTypes?: HazardType[];
  /** Forecast issue time of the mock events, and the "now" of the API and the browser. */
  viewTime: Date;
};

export type ExposedAdminAreaRow = {
  name: string;
  exposedPopulation: string;
};

export type ExposedAdminAreaLevel = {
  /** As shown in "Total exposed {label}:" */
  label: string;
  rowCount: number;
  firstRow: ExposedAdminAreaRow;
};

const viewTime = new Date('2026-09-22T00:00:00Z');

export const noEvents = {
  countryCodes: ['MWI', 'UGA'],
  mockScenario: MockScenario.noEvents,
  viewTime,
} satisfies Scenario;

export const singleEvent = {
  countryCodes: ['MWI'],
  mockScenario: MockScenario.events,
  hazardTypes: [HazardType.floods],
  viewTime,
  event: {
    eventName: 'Chikwawa',
    heading: 'Flood - Chikwawa - 24 Sep 2026',
    chips: ['High', 'Imminent', 'Trigger reached'],
    start: 'In 2 days, 24 Sep 2026',
    timestamps: 'Event created: 22 Sep 2026, Last updated: 22 Sep 2026',
    advisory: 'Trigger - activate EAP',
    riverDischarge: {
      returnPeriod: '20 year return period',
      stationCode: 'G5694',
    },
    dataSourceTitles: [
      'Forecast river discharge',
      'Flood depth maps',
      'Population counts',
    ],
    defaultLayerLabels: ['Exposed population', 'Flood depth'],
    exposedAdminAreas: {
      label: 'traditional authorities',
      rowCount: 3,
      firstRow: { name: 'TA Katunga', exposedPopulation: '988' },
    } satisfies ExposedAdminAreaLevel,
  },
} satisfies Scenario & Record<string, unknown>;

export const drillDown = {
  countryCodes: ['SSD'],
  mockScenario: MockScenario.events,
  hazardTypes: [HazardType.floods],
  viewTime,
  event: {
    eventName: 'G5100',
    // Admin level 1 (states) is skipped, so the event opens at counties.
    initialLevel: {
      label: 'counties',
      rowCount: 4,
      firstRow: { name: 'Twic East', exposedPopulation: '122,052' },
    } satisfies ExposedAdminAreaLevel,
    drilledInto: {
      name: 'Twic East',
      placeCode: 'SS0310',
      selectedAreaLabel: 'Twic East County',
      level: {
        label: 'payams',
        rowCount: 5,
        firstRow: { name: 'Kongor', exposedPopulation: '50,365' },
      } satisfies ExposedAdminAreaLevel,
    },
    // A payam has no exposed admin areas below it, so drilling into one selects it.
    deepestLevel: { name: 'Kongor', placeCode: 'SS031002' },
  },
} satisfies Scenario & Record<string, unknown>;

export const multipleEvents = {
  countryCodes: ['UGA'],
  mockScenario: MockScenario.events,
  hazardTypes: [HazardType.floods],
  viewTime,
  // In display order: by start date.
  events: [
    {
      eventName: 'Mayanja (83218)',
      chips: ['High', 'Ongoing', 'Trigger reached'],
    },
    { eventName: 'Mitano (84267)', chips: ['Low', 'Imminent'] },
    {
      eventName: 'Mpologoma at Budumba (82217)',
      chips: ['Medium', 'Imminent'],
    },
    // High, but beyond the trigger lead time, so it does not trigger.
    { eventName: 'Manafwa at Butaleja (82212)', chips: ['High', 'Imminent'] },
  ],
} satisfies Scenario & Record<string, unknown>;

/** Every country any scenario needs, so the database is reset only once per run. */
export const allScenarioCountryCodes = [
  ...new Set(
    [noEvents, singleEvent, drillDown, multipleEvents].flatMap(
      (scenario) => scenario.countryCodes,
    ),
  ),
];
