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
    advisory: 'Trigger - activate EAP',
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
      selectedAreaLabel: 'Twic East County',
      level: {
        label: 'payams',
        rowCount: 5,
        firstRow: { name: 'Kongor', exposedPopulation: '50,365' },
      } satisfies ExposedAdminAreaLevel,
    },
  },
} satisfies Scenario & Record<string, unknown>;

/** Every country any scenario needs, so the database is reset only once per run. */
export const allScenarioCountryCodes = [
  ...new Set(
    [noEvents, singleEvent, drillDown].flatMap(
      (scenario) => scenario.countryCodes,
    ),
  ),
];
