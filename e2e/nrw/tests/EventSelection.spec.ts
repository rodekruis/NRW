import { expect, test, useScenario, visualTest } from '@nrw-e2e/nrw/fixtures';
import { getEvents } from '@nrw-e2e/nrw/helpers/events';
import { singleEvent } from '@nrw-e2e/nrw/scenarios';

const { countryCodes, viewTime } = singleEvent;
const { eventName } = singleEvent.event;

useScenario(singleEvent);

test('clicking an event card opens the event and hides the event markers', async ({
  nrwPage,
}) => {
  // Arrange
  await nrwPage.goto({ countryCodes });

  // Act
  await nrwPage.eventsPanel.openEvent(eventName);

  // Assert
  await expect(nrwPage.eventsPanel.openButton(eventName)).toHaveCount(0);
  await expect(nrwPage.page).toHaveURL(/[?&]event=\d+/);
  await expect(nrwPage.map.eventMarkers).toHaveCount(0);
  await expect(nrwPage.layerPanel.openButton).toBeVisible();
});

test('going back to all events shows all events and the event markers again', async ({
  nrwPage,
}) => {
  // Arrange
  await nrwPage.goto({ countryCodes });
  await nrwPage.eventsPanel.openEvent(eventName);
  await expect(nrwPage.eventsPanel.openButton(eventName)).toHaveCount(0);

  // Act
  await nrwPage.eventsPanel.showAllEvents();

  // Assert
  await expect(nrwPage.eventsPanel.openButton(eventName)).toBeVisible();
  await expect(nrwPage.page).not.toHaveURL(/[?&]event=/);
  await expect(nrwPage.eventDetail.root).toHaveCount(0);
  await expect(nrwPage.map.eventMarkers).toHaveCount(1);
  await expect(nrwPage.layerPanel.openButton).toHaveCount(0);
});

test('opening an event link opens the event', async ({ nrwPage }) => {
  // Arrange
  const [event] = await getEvents(countryCodes, viewTime);

  // Act
  await nrwPage.goto({ countryCodes, eventId: event.eventId });

  // Assert
  await expect(nrwPage.eventsPanel.eventCards.first()).toContainText(
    event.eventName,
  );
  await expect(nrwPage.eventsPanel.openButton(eventName)).toHaveCount(0);
  await expect(nrwPage.map.eventMarkers).toHaveCount(0);
});

test('clicking an event marker opens the event', async ({ nrwPage }) => {
  // Arrange
  await nrwPage.goto({ countryCodes });

  // Act
  await nrwPage.map.eventMarkerButton(eventName).click();

  // Assert
  await expect(nrwPage.eventsPanel.openButton(eventName)).toHaveCount(0);
  await expect(nrwPage.page).toHaveURL(/[?&]event=\d+/);
});

test(
  'event opened: page layout with the map zoomed to the exposed admin areas',
  visualTest,
  async ({ nrwPage }) => {
    // Arrange
    await nrwPage.goto({ countryCodes });

    // Act
    await nrwPage.eventsPanel.openEvent(eventName);
    await nrwPage.page.waitForLoadState('networkidle');

    // Assert
    await expect(nrwPage.page).toHaveScreenshot('event-opened.png');
  },
);
