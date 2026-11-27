import { expect, test, useScenario, visualTest } from '@nrw-e2e/nrw/fixtures';
import { singleEvent } from '@nrw-e2e/nrw/scenarios';

const {
  eventName,
  heading,
  chips,
  start,
  timestamps,
  advisory,
  exposedAdminAreas,
  riverDischarge,
  dataSourceTitles,
} = singleEvent.event;

useScenario(singleEvent);

test.beforeEach(async ({ nrwPage }) => {
  await nrwPage.goto({ countryCodes: singleEvent.countryCodes });
  await nrwPage.eventsPanel.openEvent(eventName);
});

test('shows the advisory', async ({ nrwPage }) => {
  // Assert
  await expect(nrwPage.eventDetail.root).toContainText(advisory);
});

test('shows the exposed admin areas', async ({ nrwPage }) => {
  // Assert
  await expect(
    nrwPage.exposedAdminAreas.totalAreasText(exposedAdminAreas.label),
  ).toBeVisible();
  await expect(nrwPage.exposedAdminAreas.rows).toHaveCount(
    exposedAdminAreas.rowCount,
  );
  await expect(nrwPage.exposedAdminAreas.firstRowCells).toHaveText([
    exposedAdminAreas.firstRow.name,
    exposedAdminAreas.firstRow.exposedPopulation,
  ]);
  await expect(nrwPage.exposedAdminAreas.backButton).toHaveCount(0);
});

test('shows the chips and the event name with its start date', async ({
  nrwPage,
}) => {
  // Arrange
  const eventCard = nrwPage.eventsPanel.eventCard(eventName);

  // Assert
  for (const chip of chips) {
    await expect(eventCard.getByText(chip, { exact: true })).toBeVisible();
  }
  await expect(eventCard.getByRole('heading', { name: heading })).toBeVisible();
});

test('shows when the event starts and when it was created and updated', async ({
  nrwPage,
}) => {
  // Assert
  await expect(nrwPage.eventDetail.root).toContainText(`Starts:${start}`);
  await expect(nrwPage.eventDetail.root).toContainText(timestamps);
});

test('expanding the river discharge forecast shows the station and the chart', async ({
  nrwPage,
}) => {
  // Arrange
  const { riverDischargeToggle, riverDischargeChart } = nrwPage.eventDetail;
  await expect(riverDischargeToggle).toContainText(riverDischarge.returnPeriod);
  await expect(riverDischargeChart).toHaveCount(0);

  // Act
  await riverDischargeToggle.click();

  // Assert
  await expect(riverDischargeToggle).toHaveAttribute('aria-expanded', 'true');
  await expect(nrwPage.eventDetail.root).toContainText(
    riverDischarge.stationCode,
  );
  await expect(riverDischargeChart).toBeVisible();
});

test('river discharge chart', visualTest, async ({ nrwPage }) => {
  // Act
  await nrwPage.eventDetail.riverDischargeToggle.click();

  // Assert
  await expect(nrwPage.eventDetail.riverDischargeChart).toHaveScreenshot(
    'river-discharge-chart.png',
  );
});

test('expanding a data source shows its details', async ({ nrwPage }) => {
  // Arrange
  for (const title of dataSourceTitles) {
    await expect(nrwPage.eventDetail.dataSourceToggle(title)).toBeVisible();
  }
  const [firstDataSourceTitle] = dataSourceTitles;
  const details = nrwPage.eventDetail.dataSourceDetails(firstDataSourceTitle);
  await expect(details).toHaveCount(0);

  // Act
  await nrwPage.eventDetail.dataSourceToggle(firstDataSourceTitle).click();

  // Assert
  for (const label of [
    'Dataset:',
    'Source:',
    'Updated:',
    'Description:',
    'More info:',
  ]) {
    await expect(details).toContainText(label);
  }
  await expect(details.getByRole('link')).toBeVisible();
});
