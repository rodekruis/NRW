import { expect, test, useScenario, visualTest } from '@nrw-e2e/nrw/fixtures';
import { LayerName } from '@nrw-e2e/nrw/helpers/enums';
import { getEvents } from '@nrw-e2e/nrw/helpers/events';
import { renderPdfPages } from '@nrw-e2e/nrw/helpers/pdf';
import { singleEvent } from '@nrw-e2e/nrw/scenarios';

const { countryCodes, viewTime } = singleEvent;
const exportDate = viewTime.toISOString().slice(0, 10);

useScenario(singleEvent);

test('exporting all events downloads a PDF of the country', async ({
  nrwPage,
}) => {
  // Arrange
  await nrwPage.goto({ countryCodes });

  // Act
  const download = await nrwPage.pdfExport.export();

  // Assert
  expect(download.suggestedFilename()).toBe(
    `national-risk-watch-${countryCodes[0]}-${exportDate}.pdf`,
  );
});

test('exporting an opened event downloads a PDF of the event', async ({
  nrwPage,
}) => {
  // Arrange
  const [event] = await getEvents(countryCodes, viewTime);
  await nrwPage.goto({ countryCodes, eventId: event.eventId });

  // Act
  const download = await nrwPage.pdfExport.export();

  // Assert
  expect(download.suggestedFilename()).toBe(
    `national-risk-watch-${countryCodes[0]}-event${String(event.eventId)}-${exportDate}.pdf`,
  );
});

// The PDF is composed from captures of the panels and the map, so it can break
// while the page itself renders fine.
test(
  'PDF of an opened event with the river discharge chart',
  visualTest,
  async ({ nrwPage, context }) => {
    // Arrange
    // A link opens the map at the event directly; a click animates the zoom,
    // and the export captures the map only once.
    const [event] = await getEvents(countryCodes, viewTime);
    await nrwPage.goto({
      countryCodes,
      eventId: event.eventId,
      layers: [LayerName.exposedPopulation, LayerName.floodDepth],
    });
    await nrwPage.eventDetail.riverDischargeToggle.click();
    await expect(nrwPage.eventDetail.riverDischargeChart).toBeVisible();

    // Act
    const download = await nrwPage.pdfExport.export();

    // Assert
    const pdfPages = await renderPdfPages({ context, download });
    for (const [index, pdfPage] of (await pdfPages.all()).entries()) {
      await expect(pdfPage).toHaveScreenshot(
        `event-pdf-page-${String(index + 1)}.png`,
      );
    }
  },
);
