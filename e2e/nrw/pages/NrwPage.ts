import { Page } from '@playwright/test';

import { EventDetail } from '@nrw-e2e/nrw/pages/components/EventDetail';
import { EventsPanel } from '@nrw-e2e/nrw/pages/components/EventsPanel';
import { ExposedAdminAreas } from '@nrw-e2e/nrw/pages/components/ExposedAdminAreas';
import { LayerPanel } from '@nrw-e2e/nrw/pages/components/LayerPanel';
import { NrwMap } from '@nrw-e2e/nrw/pages/components/NrwMap';

/**
 * Page object for the standalone NRW page.
 *
 * Components hold the locators and actions, one per region of the screen.
 */
export class NrwPage {
  readonly page: Page;
  readonly eventsPanel: EventsPanel;
  readonly eventDetail: EventDetail;
  readonly exposedAdminAreas: ExposedAdminAreas;
  readonly map: NrwMap;
  readonly layerPanel: LayerPanel;

  constructor(page: Page) {
    this.page = page;
    this.eventsPanel = new EventsPanel(page);
    this.eventDetail = new EventDetail(page);
    this.exposedAdminAreas = new ExposedAdminAreas(page);
    this.map = new NrwMap(page);
    this.layerPanel = new LayerPanel(page);
  }

  async goto({
    countryCodes,
    eventId,
  }: {
    countryCodes: string[];
    eventId?: number;
  }): Promise<void> {
    const searchParams = new URLSearchParams({
      countries: countryCodes.join(','),
    });
    if (eventId !== undefined) {
      searchParams.set('event', String(eventId));
    }
    await this.page.goto(`/?${searchParams.toString()}`);
    await this.waitForMapLoaded();
  }

  async waitForMapLoaded(): Promise<void> {
    await this.map.canvas.waitFor({ state: 'visible' });
    await this.page.waitForLoadState('networkidle');
  }
}
