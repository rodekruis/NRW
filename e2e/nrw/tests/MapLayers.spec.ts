import { expect, test, useScenario, visualTest } from '@nrw-e2e/nrw/fixtures';
import { singleEvent } from '@nrw-e2e/nrw/scenarios';

useScenario(singleEvent);

test('showing the population layer adds it to the map', async ({ nrwPage }) => {
  // Arrange
  await nrwPage.goto({ countryCodes: singleEvent.countryCodes });
  await nrwPage.eventsPanel.openEvent(singleEvent.event.eventName);
  await nrwPage.layerPanel.open();
  await expect(nrwPage.layerPanel.openButton).toHaveAttribute(
    'aria-expanded',
    'true',
  );
  const populationLayerToggle =
    nrwPage.layerPanel.layerToggle('Population density');
  await expect(populationLayerToggle).not.toBeChecked();

  // Act
  await populationLayerToggle.click();

  // Assert
  await expect(populationLayerToggle).toBeChecked();
});

test('population layer on the map', visualTest, async ({ nrwPage }) => {
  // Arrange
  await nrwPage.goto({ countryCodes: singleEvent.countryCodes });
  await nrwPage.eventsPanel.openEvent(singleEvent.event.eventName);
  await nrwPage.layerPanel.open();

  // Act
  await nrwPage.layerPanel.layerToggle('Population density').click();
  await nrwPage.page.waitForLoadState('networkidle');

  // Assert
  await expect(nrwPage.map.canvas).toHaveScreenshot(
    'event-population-layer.png',
  );
});
