import { expect, test, useScenario, visualTest } from '@nrw-e2e/nrw/fixtures';
import { singleEvent } from '@nrw-e2e/nrw/scenarios';

const { eventName, defaultLayerLabels } = singleEvent.event;

useScenario(singleEvent);

test('showing the population layer adds it to the map', async ({ nrwPage }) => {
  // Arrange
  await nrwPage.goto({ countryCodes: singleEvent.countryCodes });
  await nrwPage.eventsPanel.openEvent(eventName);
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
  await nrwPage.eventsPanel.openEvent(eventName);
  await nrwPage.layerPanel.open();

  // Act
  await nrwPage.layerPanel.layerToggle('Population density').click();
  await nrwPage.page.waitForLoadState('networkidle');

  // Assert
  await expect(nrwPage.map.canvas).toHaveScreenshot(
    'event-population-layer.png',
  );
});

test('opening a flood event shows the exposed population and flood depth layers', async ({
  nrwPage,
}) => {
  // Arrange
  await nrwPage.goto({ countryCodes: singleEvent.countryCodes });

  // Act
  await nrwPage.eventsPanel.openEvent(eventName);

  // Assert
  await nrwPage.layerPanel.open();
  for (const label of defaultLayerLabels) {
    await expect(nrwPage.layerPanel.layerToggle(label)).toBeChecked();
    await expect(nrwPage.legendBanner.item(label)).toBeVisible();
  }
});

test('hiding the flood depth layer removes it from the legend and the URL', async ({
  nrwPage,
}) => {
  // Arrange
  await nrwPage.goto({ countryCodes: singleEvent.countryCodes });
  await nrwPage.eventsPanel.openEvent(eventName);
  await nrwPage.layerPanel.open();
  const floodDepthToggle = nrwPage.layerPanel.layerToggle('Flood depth');
  await expect(floodDepthToggle).toBeChecked();

  // Act
  await floodDepthToggle.click();

  // Assert
  await expect(floodDepthToggle).not.toBeChecked();
  await expect(nrwPage.legendBanner.item('Flood depth')).toHaveCount(0);
  await expect(nrwPage.page).toHaveURL(/[?&]layers=exposedPopulation(&|$)/);
});

test('all events: the legend explains the event markers', async ({
  nrwPage,
}) => {
  // Act
  await nrwPage.goto({ countryCodes: singleEvent.countryCodes });

  // Assert
  await expect(nrwPage.legendBanner.root).toContainText('Alert level:');
  await expect(nrwPage.legendBanner.root).toContainText('Event type:');
});

test('hiding all layers asks to turn on layers in the legend', async ({
  nrwPage,
}) => {
  // Arrange
  await nrwPage.goto({ countryCodes: singleEvent.countryCodes });
  await nrwPage.eventsPanel.openEvent(eventName);
  await nrwPage.layerPanel.open();

  // Act
  for (const label of defaultLayerLabels) {
    await nrwPage.layerPanel.layerToggle(label).click();
  }

  // Assert
  await expect(nrwPage.legendBanner.noLayersMessage).toBeVisible();
});
