import { Locator, Page } from '@playwright/test';

export class EventsPanel {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  get eventCards(): Locator {
    return this.page.locator('[class*="nrw-event-card"]');
  }

  get hoveredEventCards(): Locator {
    return this.page.locator('[class*="nrw-event-card"][class*="hovered"]');
  }

  /** Only shown while an event is open. */
  get allEventsButton(): Locator {
    return this.page.getByRole('button', { name: /^All events/ });
  }

  eventCard(eventName: string): Locator {
    return this.eventCards.filter({ hasText: eventName });
  }

  /**
   * Only a collapsed card has an open button. It is labelled by the whole card
   * header, so match on the labelling rather than on a name that admin areas
   * inside an open card (e.g. "Chikwawa Boma") can also contain.
   */
  openButton(eventName: string): Locator {
    return this.eventCard(eventName).locator('button[aria-labelledby]');
  }

  async openEvent(eventName: string): Promise<void> {
    await this.openButton(eventName).click();
  }

  async showAllEvents(): Promise<void> {
    await this.allEventsButton.click();
  }
}
