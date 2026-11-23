import { expect, test, useScenario } from '@nrw-e2e/nrw/fixtures';
import { noEvents } from '@nrw-e2e/nrw/scenarios';

useScenario(noEvents);

test('single country: shows map zoomed to country without event markers', async ({
  nrwPage,
}) => {
  // Act
  await nrwPage.goto({ countryCodes: [noEvents.countryCodes[0]] });

  // Assert
  await expect(nrwPage.map.eventMarkers).toHaveCount(0);
});

test('multi-country: shows map zoomed to countries without event markers', async ({
  nrwPage,
}) => {
  // Act
  await nrwPage.goto({ countryCodes: noEvents.countryCodes });

  // Assert
  await expect(nrwPage.map.eventMarkers).toHaveCount(0);
});
