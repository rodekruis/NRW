import { test as setup } from '@playwright/test';

import { resetDb } from '@nrw-e2e/nrw/helpers/reset';
import { allScenarioCountryCodes } from '@nrw-e2e/nrw/scenarios';

setup('reset database for all scenario countries', async () => {
  await resetDb(allScenarioCountryCodes);
});
