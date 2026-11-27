import { expect, test, useScenario } from '@nrw-e2e/nrw/fixtures';
import { drillDown } from '@nrw-e2e/nrw/scenarios';

const { eventName, initialLevel, drilledInto } = drillDown.event;

useScenario(drillDown);

test('drilling down into a row shows its exposed admin areas, and back returns', async ({
  nrwPage,
}) => {
  // Arrange
  const { exposedAdminAreas } = nrwPage;
  await nrwPage.goto({ countryCodes: drillDown.countryCodes });
  await nrwPage.eventsPanel.openEvent(eventName);
  await expect(
    exposedAdminAreas.totalAreasText(initialLevel.label),
  ).toBeVisible();
  await expect(exposedAdminAreas.rows).toHaveCount(initialLevel.rowCount);
  await expect(exposedAdminAreas.firstRowCells).toHaveText([
    initialLevel.firstRow.name,
    initialLevel.firstRow.exposedPopulation,
  ]);
  await expect(exposedAdminAreas.backButton).toHaveCount(0);

  // Act
  await exposedAdminAreas.drillDown(drilledInto.name);

  // Assert
  await expect(exposedAdminAreas.selectedAdminArea).toHaveText(
    drilledInto.selectedAreaLabel,
  );
  await expect(
    exposedAdminAreas.totalAreasText(drilledInto.level.label),
  ).toBeVisible();
  await expect(exposedAdminAreas.rows).toHaveCount(drilledInto.level.rowCount);
  await expect(exposedAdminAreas.firstRowCells).toHaveText([
    drilledInto.level.firstRow.name,
    drilledInto.level.firstRow.exposedPopulation,
  ]);

  // Act
  await exposedAdminAreas.drillUp();

  // Assert
  await expect(exposedAdminAreas.selectedAdminArea).toHaveCount(0);
  await expect(
    exposedAdminAreas.totalAreasText(initialLevel.label),
  ).toBeVisible();
  await expect(exposedAdminAreas.firstRowCells).toHaveText([
    initialLevel.firstRow.name,
    initialLevel.firstRow.exposedPopulation,
  ]);
});
