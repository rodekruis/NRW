"""Definitions of the IOD and FEWS NET indicators of the drought hindcast analysis."""

from enum import StrEnum

from analysis.drought_hindcast.definitions import REGION_SEASONS, RegionSeason
from analysis.drought_hindcast.download_iod import IodSource


class Indicator(StrEnum):
    SEAS5 = "seas5"
    IOD = "iod"
    FEWS_NET = "fews_net"


class IodPhase(StrEnum):
    NEGATIVE = "negative"
    POSITIVE = "positive"


class IodAlertRule(StrEnum):
    """When the index counts as far enough towards the phase that goes with drought."""

    # In the outer third of its own values for that run month, in the other years.
    OWN_TERCILE = "own_tercile"
    # Beyond the threshold in degrees that commonly defines an IOD event.
    FIXED_THRESHOLD = "fixed_threshold"


class FewsNetAlertRule(StrEnum):
    """When the share of the region that is projected in Phase 3 or worse gives an alert."""

    # In the upper third of the region's own shares for that run month, in the other years.
    OWN_TERCILE = "own_tercile"
    # At least a fixed share of the region.
    FIXED_SHARE = "fixed_share"
    # The share is projected to grow from the current situation, by an amount in the
    # upper third of the region's own changes for that run month, in the other years.
    WORSENING = "worsening"


# Turns the index into a value that is higher when a drought is more likely.
IOD_PHASE_SIGNS: dict[IodPhase, int] = {IodPhase.NEGATIVE: -1, IodPhase.POSITIVE: 1}

# The phase that goes with a dry season: negative for the short rains of East Africa,
# positive for the summer rains of Zimbabwe.
IOD_DROUGHT_PHASES: dict[str, IodPhase] = {
    "ETH Southern OND": IodPhase.NEGATIVE,
    "KEN National OND": IodPhase.NEGATIVE,
    "ZWE National Oct-Mar": IodPhase.POSITIVE,
    "ZWE National OND": IodPhase.POSITIVE,
    "ZWE National JFM": IodPhase.POSITIVE,
}

# The source and rule that the results are reported for, unless stated otherwise.
MAIN_IOD_SOURCE = IodSource.OISST_WEEKLY
MAIN_IOD_ALERT_RULE = IodAlertRule.OWN_TERCILE
# The index is averaged over this many months before the run month. One month is the
# proposed rule; four months at the October run is the setup of the Zimbabwe drought trigger (June to
# September, against Jan-Mar rainfall).
IOD_INDEX_MONTH_COUNTS = (1, 4)
MAIN_IOD_INDEX_MONTH_COUNT = 1
# Degrees Celsius, as used by the Bureau of Meteorology and NOAA CPC.
IOD_EVENT_THRESHOLD = 0.4


# A run uses the latest report from at least this many months before the run month.
# Recent reports reach the warehouse five to six weeks after the first of their month, so
# one month assumes last month's report is just in time, and two months is the careful choice.
FEWS_NET_REPORT_LAG_MONTHS = (1, 2)
MAIN_FEWS_NET_REPORT_LAG_MONTHS = 1
# Up to 2018 there is a report every three or four months.
FEWS_NET_MAXIMUM_REPORT_AGE_MONTHS = 6
# The current situation is classified three times a year; a projection is compared with
# the latest one, up to this many months before its report.
FEWS_NET_MAXIMUM_CURRENT_SITUATION_AGE_MONTHS = 4
MAIN_FEWS_NET_ALERT_RULE = FewsNetAlertRule.OWN_TERCILE
FEWS_NET_MINIMUM_AREA_SHARE = 0.2
# Region-seasons with fewer seasons than this are not scored.
FEWS_NET_MINIMUM_SEASON_COUNT = 10


def get_fews_net_alert_column(rule: FewsNetAlertRule) -> str:
    return f"alert_at_{rule}"


def get_iod_alert_column(rule: IodAlertRule) -> str:
    return f"alert_at_{rule}"


def get_iod_region_seasons() -> list[RegionSeason]:
    return [
        region_season
        for region_season in REGION_SEASONS
        if region_season.name in IOD_DROUGHT_PHASES
    ]
