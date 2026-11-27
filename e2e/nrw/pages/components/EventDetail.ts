import { Locator, Page } from '@playwright/test';

export class EventDetail {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  get root(): Locator {
    return this.page.locator('[class*="nrw-event-detail"]');
  }

  get riverDischargeToggle(): Locator {
    return this.root.getByRole('button', {
      name: /^River discharge forecast:/,
    });
  }

  get riverDischargeChart(): Locator {
    return this.root.getByRole('img', {
      name: /^River discharge forecast chart/,
    });
  }

  dataSourceToggle(title: string): Locator {
    return this.root.getByRole('button', { name: title, exact: true });
  }

  /** The expanded details sit right after the data source's toggle. */
  dataSourceDetails(title: string): Locator {
    return this.dataSourceToggle(title).locator('xpath=following-sibling::ul');
  }
}
