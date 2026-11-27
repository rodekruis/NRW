import { Page } from '@playwright/test';

import { LayerName } from '@nrw-e2e/nrw/helpers/enums';
import { AdminAreaBreadcrumbs } from '@nrw-e2e/nrw/pages/components/AdminAreaBreadcrumbs';
import { EventDetail } from '@nrw-e2e/nrw/pages/components/EventDetail';
import { EventsPanel } from '@nrw-e2e/nrw/pages/components/EventsPanel';
import { ExposedAdminAreas } from '@nrw-e2e/nrw/pages/components/ExposedAdminAreas';
import { LayerPanel } from '@nrw-e2e/nrw/pages/components/LayerPanel';
import { LegendBanner } from '@nrw-e2e/nrw/pages/components/LegendBanner';
import { NrwMap } from '@nrw-e2e/nrw/pages/components/NrwMap';
import { PdfExport } from '@nrw-e2e/nrw/pages/components/PdfExport';

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
  readonly breadcrumbs: AdminAreaBreadcrumbs;
  readonly legendBanner: LegendBanner;
  readonly pdfExport: PdfExport;

  constructor(page: Page) {
    this.page = page;
    this.eventsPanel = new EventsPanel(page);
    this.eventDetail = new EventDetail(page);
    this.exposedAdminAreas = new ExposedAdminAreas(page);
    this.map = new NrwMap(page);
    this.layerPanel = new LayerPanel(page);
    this.breadcrumbs = new AdminAreaBreadcrumbs(page);
    this.legendBanner = new LegendBanner(page);
    this.pdfExport = new PdfExport(page);
  }

  async goto({
    countryCodes,
    eventId,
    placeCode,
    layers,
  }: {
    countryCodes: string[];
    eventId?: number;
    placeCode?: string;
    layers?: LayerName[];
  }): Promise<void> {
    const searchParams = new URLSearchParams({
      countries: countryCodes.join(','),
    });
    if (eventId !== undefined) {
      searchParams.set('event', String(eventId));
    }
    if (placeCode !== undefined) {
      searchParams.set('placeCode', placeCode);
    }
    if (layers !== undefined) {
      searchParams.set('layers', layers.join(','));
    }

    await this.page.goto(`/?${searchParams.toString()}`);
    await this.waitForMapLoaded();
  }

  async waitForMapLoaded(): Promise<void> {
    await this.map.canvas.waitFor({ state: 'visible' });
    await this.page.waitForLoadState('networkidle');
  }
}
