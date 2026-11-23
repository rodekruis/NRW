import { test as base } from '@playwright/test';

import { mockDb } from '@nrw-e2e/nrw/helpers/mock';
import { freezeEventsViewTime } from '@nrw-e2e/nrw/helpers/view-time';
import { NrwPage } from '@nrw-e2e/nrw/pages/NrwPage';
import { Scenario } from '@nrw-e2e/nrw/scenarios';

export { expect } from '@playwright/test';

export const test = base.extend<{ nrwPage: NrwPage }>({
  nrwPage: async ({ page }, use) => {
    await use(new NrwPage(page));
  },
});

/**
 * Loads the scenario's events once for the enclosing `describe` (or file), and
 * pins "now" for both the API and the browser before every test.
 */
export function useScenario(scenario: Scenario): void {
  test.beforeAll(async () => {
    await mockDb({
      scenario: scenario.mockScenario,
      countryCodes: scenario.countryCodes,
      hazardTypes: scenario.hazardTypes,
      issuedAt: scenario.viewTime,
    });
  });

  test.beforeEach(async ({ page }) => {
    await page.clock.setFixedTime(scenario.viewTime);
    await freezeEventsViewTime(page, scenario.viewTime);
  });
}
