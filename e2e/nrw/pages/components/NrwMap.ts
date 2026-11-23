import { Locator, Page } from '@playwright/test';

export class NrwMap {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  get canvas(): Locator {
    return this.page.locator('.mapboxgl-canvas');
  }

  get eventMarkers(): Locator {
    return this.page.locator('.mapboxgl-marker:has([class*="event-marker"])');
  }

  get hoveredEventMarkers(): Locator {
    return this.page.locator(
      '.mapboxgl-marker [class*="event-marker"][class*="hovered"]',
    );
  }

  eventMarkerButton(eventName: string): Locator {
    return this.eventMarkers.filter({ hasText: eventName }).getByRole('button');
  }
}
