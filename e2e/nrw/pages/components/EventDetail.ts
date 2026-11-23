import { Locator, Page } from '@playwright/test';

export class EventDetail {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  get root(): Locator {
    return this.page.locator('[class*="nrw-event-detail"]');
  }
}
