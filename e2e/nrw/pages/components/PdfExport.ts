import { Download, Locator, Page } from '@playwright/test';

export class PdfExport {
  readonly page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  get exportButton(): Locator {
    return this.page.getByRole('button', { name: 'Export view' });
  }

  async export(): Promise<Download> {
    const downloadPromise = this.page.waitForEvent('download');
    await this.exportButton.click();
    return downloadPromise;
  }
}
