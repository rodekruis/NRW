import { addHours } from 'date-fns';

import { HazardType } from '@api-service/src/shared-enums';

const HOURS_PER_DAY = 24;

// Expected time between two forecasts of the same hazard type.
const FORECAST_INTERVAL_HOURS: Record<HazardType, number> = {
  [HazardType.floods]: HOURS_PER_DAY,
  [HazardType.compoundFloods]: HOURS_PER_DAY,
  [HazardType.tropicalCyclone]: 6,
  [HazardType.drought]: 31 * HOURS_PER_DAY,
};

// Tolerance on top of the forecast interval, covering day-to-day variation in data availability and processing time.
const FORECAST_INTERVAL_TOLERANCE_FACTOR = 1.1;

// forecastStaleAt: the moment a newer forecast is overdue, i.e. issuedAt + 110% of the hazard's forecast interval.
export function getForecastStaleAt({
  hazardType,
  issuedAt,
}: {
  hazardType: HazardType;
  issuedAt: Date;
}): Date {
  const staleAfterHours =
    FORECAST_INTERVAL_HOURS[hazardType] * FORECAST_INTERVAL_TOLERANCE_FACTOR;
  return addHours(issuedAt, staleAfterHours);
}
