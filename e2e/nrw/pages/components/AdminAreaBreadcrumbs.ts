import { Locator, Page } from '@playwright/test';

export class AdminAreaBreadcrumbs {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  get root(): Locator {
    return this.page.getByRole('navigation', { name: 'breadcrumb' });
  }

  get currentCrumb(): Locator {
    return this.root.locator('[aria-current="location"]');
  }

  crumbButton(label: string): Locator {
    return this.root.getByRole('button', { name: label, exact: true });
  }

  async goTo(label: string): Promise<void> {
    await this.crumbButton(label).click();
  }
}
