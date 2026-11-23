import { expect, test, useScenario } from '@nrw-e2e/nrw/fixtures';
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
