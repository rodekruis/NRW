import { expect, test, useScenario, visualTest } from '@nrw-e2e/nrw/fixtures';
import { multipleEvents, singleEvent } from '@nrw-e2e/nrw/scenarios';

test.describe('single event', () => {
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
});

test.describe('multiple events', () => {
  useScenario(multipleEvents);

  test.beforeEach(async ({ nrwPage }) => {
    await nrwPage.goto({ countryCodes: multipleEvents.countryCodes });
  });

  test('shows an event card and an event marker per event, with its chips', async ({
    nrwPage,
  }) => {
    // Assert
    await expect(nrwPage.eventsPanel.eventCards).toHaveCount(
      multipleEvents.events.length,
    );
    await expect(nrwPage.map.eventMarkers).toHaveCount(
      multipleEvents.events.length,
    );
    for (const event of multipleEvents.events) {
      const eventCard = nrwPage.eventsPanel.eventCard(event.eventName);
      for (const chip of event.chips) {
        await expect(eventCard.getByText(chip, { exact: true })).toBeVisible();
      }
    }
  });

  test('opening an event shows only that event', async ({ nrwPage }) => {
    // Arrange
    const [, secondEvent] = multipleEvents.events;

    // Act
    await nrwPage.eventsPanel.openEvent(secondEvent.eventName);

    // Assert
    await expect(nrwPage.eventsPanel.eventCards).toHaveCount(1);
    await expect(
      nrwPage.eventsPanel.eventCard(secondEvent.eventName),
    ).toBeVisible();
    await expect(nrwPage.map.eventMarkers).toHaveCount(0);
  });
});
