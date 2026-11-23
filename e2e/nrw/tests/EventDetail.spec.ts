import { expect, test, useScenario } from '@nrw-e2e/nrw/fixtures';
import { singleEvent } from '@nrw-e2e/nrw/scenarios';

const { eventName, advisory, exposedAdminAreas } = singleEvent.event;

useScenario(singleEvent);

test.beforeEach(async ({ nrwPage }) => {
  await nrwPage.goto({ countryCodes: singleEvent.countryCodes });
  await nrwPage.eventsPanel.openEvent(eventName);
});

test('shows the advisory', async ({ nrwPage }) => {
  // Assert
  await expect(nrwPage.eventDetail.root).toContainText(advisory);
});

test('shows the exposed admin areas', async ({ nrwPage }) => {
  // Assert
  await expect(
    nrwPage.exposedAdminAreas.totalAreasText(exposedAdminAreas.label),
  ).toBeVisible();
  await expect(nrwPage.exposedAdminAreas.rows).toHaveCount(
    exposedAdminAreas.rowCount,
  );
  await expect(nrwPage.exposedAdminAreas.firstRowCells).toHaveText([
    exposedAdminAreas.firstRow.name,
    exposedAdminAreas.firstRow.exposedPopulation,
  ]);
  await expect(nrwPage.exposedAdminAreas.backButton).toHaveCount(0);
});
