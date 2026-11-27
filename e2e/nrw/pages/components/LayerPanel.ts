import { Locator, Page } from '@playwright/test';

export class LayerPanel {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  /** Only shown while an event is open. */
  get openButton(): Locator {
    return this.page.getByRole('button', { name: 'Layers', exact: true });
  }

  layerToggle(label: string): Locator {
    return this.page.getByRole('checkbox', { name: label, exact: true });
  }

  async open(): Promise<void> {
    await this.openButton.click();
  }
}
