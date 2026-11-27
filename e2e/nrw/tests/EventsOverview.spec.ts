import { expect, test, useScenario, visualTest } from '@nrw-e2e/nrw/fixtures';
import { singleEvent } from '@nrw-e2e/nrw/scenarios';

const { eventName } = singleEvent.event;

useScenario(singleEvent);

test.beforeEach(async ({ nrwPage }) => {
  await nrwPage.goto({ countryCodes: singleEvent.countryCodes });
});

test('shows event markers for active events', async ({ nrwPage }) => {
  // Assert
  await expect(nrwPage.map.eventMarkers.first()).toBeVisible();
});

test('hovering an event card highlights its event marker', async ({
  nrwPage,
}) => {
  // Act
  await nrwPage.eventsPanel.eventCard(eventName).hover();

  // Assert
  await expect(nrwPage.map.hoveredEventMarkers).toHaveCount(1);
});

test('hovering an event marker highlights its event card', async ({
  nrwPage,
}) => {
  // Act
  await nrwPage.map.eventMarkerButton(eventName).hover();

  // Assert
  await expect(nrwPage.eventsPanel.hoveredEventCards).toHaveCount(1);
});

test('page layout with the event marker', visualTest, async ({ nrwPage }) => {
  // Assert
  await expect(nrwPage.page).toHaveScreenshot('all-events.png');
});
