import { expect, test, useScenario } from '@nrw-e2e/nrw/fixtures';
import { noEvents, singleEvent } from '@nrw-e2e/nrw/scenarios';

// The map is a canvas, so screenshots are the only way to check what it draws.
// Two full-page screenshots also guard the overall layout (spacing, overlap,
// panels); other states only differ on the map, so they capture the map only.

test.describe('no events', () => {
  useScenario(noEvents);

  test('single country: map zoomed to the country', async ({ nrwPage }) => {
    // Act
    await nrwPage.goto({ countryCodes: [noEvents.countryCodes[0]] });

    // Assert
    await expect(nrwPage.map.canvas).toHaveScreenshot(
      'no-events-single-country.png',
    );
  });

  test('multi-country: map zoomed to the countries', async ({ nrwPage }) => {
    // Act
    await nrwPage.goto({ countryCodes: noEvents.countryCodes });

    // Assert
    await expect(nrwPage.map.canvas).toHaveScreenshot(
      'no-events-multi-country.png',
    );
  });
});

test.describe('single event', () => {
  useScenario(singleEvent);

  test('all events: page layout with the event marker', async ({ nrwPage }) => {
    // Act
    await nrwPage.goto({ countryCodes: singleEvent.countryCodes });

    // Assert
    await expect(nrwPage.page).toHaveScreenshot('all-events.png');
  });

  test('event opened: page layout with the map zoomed to the exposed admin areas', async ({
    nrwPage,
  }) => {
    // Arrange
    await nrwPage.goto({ countryCodes: singleEvent.countryCodes });

    // Act
    await nrwPage.eventsPanel.openEvent(singleEvent.event.eventName);
    await nrwPage.page.waitForLoadState('networkidle');

    // Assert
    await expect(nrwPage.page).toHaveScreenshot('event-opened.png');
  });

  test('event opened with the population layer', async ({ nrwPage }) => {
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
});
