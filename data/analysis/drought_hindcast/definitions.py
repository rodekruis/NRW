"""Region-seasons and alert definitions of the drought hindcast analysis."""

from dataclasses import dataclass
from enum import StrEnum

from analysis.drought_hindcast.study_area import format_region_key


@dataclass(frozen=True)
class RegionSeason:
    country_code_iso3: str
    region_name: str
    season_name: str
    # Consecutive calendar months in season order; a season may run into the next year.
    months: tuple[int, ...]
    # False for an extra season definition of a region that is already counted.
    is_in_pooled_results: bool = True

    @property
    def region_key(self) -> str:
        return format_region_key(self.country_code_iso3, self.region_name)

    @property
    def name(self) -> str:
        return f"{self.region_key} {self.season_name}"


class ForecastVariant(StrEnum):
    """How a run month within the season accounts for the season months that already passed."""

    REST_OF_SEASON = "rest_of_season"
    EARLIER_FORECAST_FOR_PAST_MONTHS = "earlier_forecast_for_past_months"
    OBSERVED_FOR_PAST_MONTHS = "observed_for_past_months"


# ETH and KEN follow seed-alert-configs.const.ts. ZWE and LSO are scored on three
# season definitions: the whole rainy season, which counts towards the pooled results,
# and its two halves.
_SOUTHERN_AFRICA_SEASONS: dict[str, tuple[int, ...]] = {
    "Oct-Mar": (10, 11, 12, 1, 2, 3),
    "OND": (10, 11, 12),
    "JFM": (1, 2, 3),
}
_POOLED_SOUTHERN_AFRICA_SEASON = "Oct-Mar"
REGION_SEASONS: list[RegionSeason] = [
    RegionSeason("ETH", "Meher", "JAS", (6, 7, 8, 9)),
    RegionSeason("ETH", "Belg", "JAS", (6, 7, 8, 9)),
    RegionSeason("ETH", "Belg", "MAM", (2, 3, 4, 5)),
    RegionSeason("ETH", "Northern", "JAS", (7, 8, 9)),
    RegionSeason("ETH", "Northern", "MAM", (3, 4, 5)),
    RegionSeason("ETH", "Southern", "OND", (10, 11, 12)),
    RegionSeason("ETH", "Southern", "MAM", (3, 4, 5)),
    RegionSeason("KEN", "National", "OND", (10, 11, 12)),
    RegionSeason("KEN", "National", "MAM", (3, 4, 5)),
    *[
        RegionSeason(
            country_code_iso3,
            "National",
            season_name,
            months,
            is_in_pooled_results=season_name == _POOLED_SOUTHERN_AFRICA_SEASON,
        )
        for country_code_iso3 in ("ZWE", "LSO")
        for season_name, months in _SOUTHERN_AFRICA_SEASONS.items()
    ],
]
POOLED_REGION_SEASONS: list[RegionSeason] = [
    region_season
    for region_season in REGION_SEASONS
    if region_season.is_in_pooled_results
]

# SEAS5 monthly data covers the start month and the five months after it.
LEAD_MONTH_COUNT = 6
RUN_MONTHS_BEFORE_SEASON = 4

# Last year of the SEAS5 hindcast (25 members); later years are forecasts (51 members).
REFERENCE_LAST_YEAR = 2016
LOWER_TERCILE = 1 / 3
UPPER_TERCILE = 2 / 3

PROBABILITY_THRESHOLDS = (0.3, 0.4, 0.5, 0.6)
# The threshold of the alert that the results are reported for, unless stated otherwise.
DEFAULT_PROBABILITY_THRESHOLD = 0.4
# IBF v1 rule: alert when enough of the region has enough members below the cell's own tercile.
AREA_RULE_MINIMUM_PROBABILITY = 0.4
AREA_RULE_MINIMUM_AREA_SHARE = 0.4
AREA_RULE_ALERT_COLUMN = "alert_area_rule"

# Share of years counted as drought, by observed season rainfall.
DROUGHT_DEFINITIONS: dict[str, float] = {"driest_third": 1 / 3, "driest_fifth": 1 / 5}


def get_probability_alert_column(threshold: float) -> str:
    return f"alert_at_probability_{threshold}"


def get_observed_drought_column(definition_name: str) -> str:
    return f"observed_drought_{definition_name}"
