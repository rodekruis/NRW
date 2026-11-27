import { expect, test, useScenario, visualTest } from '@nrw-e2e/nrw/fixtures';
import { getEvents } from '@nrw-e2e/nrw/helpers/events';
import { NrwPage } from '@nrw-e2e/nrw/pages/NrwPage';
import { drillDown } from '@nrw-e2e/nrw/scenarios';

const { eventName, initialLevel, drilledInto, deepestLevel } = drillDown.event;

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

test('drilling down shows the drill path in the breadcrumbs and the URL', async ({
  nrwPage,
}) => {
  // Arrange
  await openEvent(nrwPage);

  // Act
  await nrwPage.exposedAdminAreas.drillDown(drilledInto.name);

  // Assert
  await expectDrilledInto(nrwPage);
});

test('clicking the event breadcrumb returns to the first exposed admin level', async ({
  nrwPage,
}) => {
  // Arrange
  await openEvent(nrwPage);
  await nrwPage.exposedAdminAreas.drillDown(drilledInto.name);
  await expectDrilledInto(nrwPage);

  // Act
  await nrwPage.breadcrumbs.goTo(eventName);

  // Assert
  await expect(nrwPage.breadcrumbs.currentCrumb).toHaveText(eventName);
  await expect(
    nrwPage.exposedAdminAreas.totalAreasText(initialLevel.label),
  ).toBeVisible();
  await expect(nrwPage.page).not.toHaveURL(/[?&]placeCode=/);
});

test('opening a link to an admin area shows it drilled into', async ({
  nrwPage,
}) => {
  // Arrange
  const [event] = await getEvents(drillDown.countryCodes, drillDown.viewTime);

  // Act
  await nrwPage.goto({
    countryCodes: drillDown.countryCodes,
    eventId: event.eventId,
    placeCode: drilledInto.placeCode,
  });

  // Assert
  await expectDrilledInto(nrwPage);
});

test('drilling into an admin area without exposed admin areas below selects it', async ({
  nrwPage,
}) => {
  // Arrange
  const { exposedAdminAreas } = nrwPage;
  await openEvent(nrwPage);
  await exposedAdminAreas.drillDown(drilledInto.name);
  await expectDrilledInto(nrwPage);

  // Act
  await exposedAdminAreas.drillDown(deepestLevel.name);

  // Assert
  await expect(exposedAdminAreas.selectedRow).toHaveText(
    new RegExp(`^${deepestLevel.name}`),
  );
  await expect(
    exposedAdminAreas.totalAreasText(drilledInto.level.label),
  ).toBeVisible();
  await expect(nrwPage.page).toHaveURL(
    new RegExp(`[?&]placeCode=${deepestLevel.placeCode}`),
  );

  // Act
  await exposedAdminAreas.drillUp();

  // Assert
  await expect(exposedAdminAreas.selectedRow).toHaveCount(0);
  await expectDrilledInto(nrwPage);
});

test(
  'drilled into an admin area: map with unselected admin areas in grey and unexposed admin areas in white',
  visualTest,
  async ({ nrwPage }) => {
    // Arrange
    await openEvent(nrwPage);
    // The flood depth layer would cover the admin area colours.
    await nrwPage.layerPanel.open();
    await nrwPage.layerPanel.layerToggle('Flood depth').click();
    await nrwPage.layerPanel.open();

    // Act
    await nrwPage.exposedAdminAreas.drillDown(drilledInto.name);
    await expectDrilledInto(nrwPage);
    await nrwPage.page.waitForLoadState('networkidle');

    // Assert
    await expect(nrwPage.map.canvas).toHaveScreenshot(
      'drilled-into-admin-area.png',
    );
  },
);

async function openEvent(nrwPage: NrwPage): Promise<void> {
  await nrwPage.goto({ countryCodes: drillDown.countryCodes });
  await nrwPage.eventsPanel.openEvent(eventName);
}

async function expectDrilledInto(nrwPage: NrwPage): Promise<void> {
  await expect(nrwPage.exposedAdminAreas.selectedAdminArea).toHaveText(
    drilledInto.selectedAreaLabel,
  );
  await expect(
    nrwPage.exposedAdminAreas.totalAreasText(drilledInto.level.label),
  ).toBeVisible();
  await expect(nrwPage.breadcrumbs.crumbButton(eventName)).toBeVisible();
  await expect(nrwPage.breadcrumbs.currentCrumb).toHaveText(drilledInto.name);
  await expect(nrwPage.page).toHaveURL(
    new RegExp(`[?&]placeCode=${drilledInto.placeCode}(&|$)`),
  );
}
