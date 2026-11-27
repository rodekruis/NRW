import { Locator, Page } from '@playwright/test';

export class ExposedAdminAreas {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  get root(): Locator {
    return this.page.locator('[class*="nrw-exposed-admin-areas"]').first();
  }

  get rows(): Locator {
    return this.root.locator('tbody tr');
  }

  get firstRowCells(): Locator {
    return this.rows.first().getByRole('cell');
  }

  /** At the deepest admin level, the selected area is a row instead of a level. */
  get selectedRow(): Locator {
    return this.rows.and(this.page.locator('[aria-current="location"]'));
  }

  get selectedAdminArea(): Locator {
    return this.root.locator('[class*="selected-admin-area-value"]');
  }

  /** Hidden from the accessibility tree while there is nothing to go back to. */
  get backButton(): Locator {
    return this.page.getByRole('button', { name: 'Back', exact: true });
  }

  totalAreasText(label: string): Locator {
    return this.root.getByText(`Total exposed ${label}:`);
  }

  async drillDown(adminAreaName: string): Promise<void> {
    await this.rows
      .getByRole('button', { name: adminAreaName, exact: true })
      .click();
  }

  async drillUp(): Promise<void> {
    await this.backButton.click();
  }
}
