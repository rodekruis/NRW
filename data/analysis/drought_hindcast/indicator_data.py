"""Data locations of the IOD and FEWS NET indicators of the drought hindcast analysis."""

from analysis.drought_hindcast.study_area import (
    DATA_DIRECTORY,
    INPUTS_DIRECTORY,
    INTERMEDIATE_DIRECTORY,
    RESULTS_DIRECTORY,
)

IOD_DIRECTORY = DATA_DIRECTORY / "iod"
IOD_MONTHLY_FILE = INTERMEDIATE_DIRECTORY / "iod_monthly.csv"

FEWS_NET_DIRECTORY = DATA_DIRECTORY / "fews_net"
FEWS_NET_CLASSIFICATIONS_DIRECTORY = FEWS_NET_DIRECTORY / "classifications"
FEWS_NET_GEOGRAPHIC_UNITS_DIRECTORY = FEWS_NET_DIRECTORY / "geographic_units"
FEWS_NET_REGION_PHASES_FILE = INTERMEDIATE_DIRECTORY / "fews_net_region_phases.csv"

IOD_ALERTS_FILE = RESULTS_DIRECTORY / "iod_alerts.csv"
IOD_SKILL_FILE = RESULTS_DIRECTORY / "iod_skill_by_lead_time.csv"
INDICATOR_CASES_FILE = RESULTS_DIRECTORY / "indicator_cases.csv"
INDICATOR_COMBINATIONS_FILE = RESULTS_DIRECTORY / "indicator_combinations.csv"
INDICATOR_RELIABLE_LEAD_TIMES_FILE = (
    RESULTS_DIRECTORY / "indicator_reliable_lead_times.csv"
)
FEWS_NET_ALERTS_FILE = RESULTS_DIRECTORY / "fews_net_alerts.csv"
FEWS_NET_SKILL_FILE = RESULTS_DIRECTORY / "fews_net_skill_by_lead_time.csv"
FEWS_NET_PROJECTION_CHECK_FILE = RESULTS_DIRECTORY / "fews_net_projection_check.csv"
FEWS_NET_AFTER_SEASON_FILE = RESULTS_DIRECTORY / "fews_net_after_season.csv"
FEWS_NET_AROUND_SEASON_END_FILE = RESULTS_DIRECTORY / "fews_net_around_season_end.csv"
FEWS_NET_SEASON_OUTCOMES_FILE = RESULTS_DIRECTORY / "fews_net_season_outcomes.csv"
OUTCOME_SKILL_FILE = RESULTS_DIRECTORY / "outcome_skill_by_lead_time.csv"
KENYA_REGION_CHECK_FILE = RESULTS_DIRECTORY / "kenya_region_check.csv"
SKILL_REVIEW_FEWS_NET_GRADES_FILE = (
    INPUTS_DIRECTORY / "skill_review_fews_net_grades.csv"
)
SKILL_REVIEW_FEWS_NET_COMPARISON_FILE = (
    RESULTS_DIRECTORY / "skill_review_fews_net_comparison.csv"
)
SKILL_REVIEW_FEWS_NET_POOLED_FILE = (
    RESULTS_DIRECTORY / "skill_review_fews_net_pooled.csv"
)
