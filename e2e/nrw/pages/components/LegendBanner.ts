import { Locator, Page } from '@playwright/test';

export class LegendBanner {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  get root(): Locator {
    return this.page.locator('[class*="nrw-legend-banner-content"]');
  }

  get noLayersMessage(): Locator {
    return this.root.getByText(
      'Turn on layers to see event exposure on the map.',
    );
  }

  /** A legend item starts with the layer label, e.g. "Flood depth:". */
  item(label: string): Locator {
    return this.root.getByText(`${label}:`, { exact: true });
  }
}
