import pandas as pd
from analysis.drought_hindcast.calculate_fews_net_alerts import (
    PROJECTION_END_COLUMN,
    PROJECTION_START_COLUMN,
    REPORT_MONTH_COLUMN,
)
from analysis.drought_hindcast.compare_fews_net_with_skill_review import (
    build_issue_month_cases,
    OFFSET_COLUMN,
)
from analysis.drought_hindcast.definitions import (
    get_observed_drought_column,
    RegionSeason,
)
from analysis.drought_hindcast.indicator_definitions import (
    FEWS_NET_MINIMUM_SEASON_COUNT,
)
from analysis.drought_hindcast.plot_skill import DEFAULT_DROUGHT_DEFINITION
from analysis.drought_hindcast.prepare_fews_net import CRISIS_OR_WORSE_COLUMN

FIRST_SEASON_YEAR = 2011
SHORT_RAINS = RegionSeason(
    country_code_iso3="KEN",
    region_name="National",
    season_name="OND",
    months=(10, 11, 12),
)
SHARE_AFTER_SEASON = 0.9


def _build_phase(
    report_month: str,
    scenario: str,
    projection_start: str,
    projection_end: str,
    share: float,
) -> dict[str, str | float | pd.Period]:
    return {
        REPORT_MONTH_COLUMN: pd.Period(report_month, freq="M"),
        "scenario": scenario,
        PROJECTION_START_COLUMN: pd.Period(projection_start, freq="M"),
        PROJECTION_END_COLUMN: pd.Period(projection_end, freq="M"),
        CRISIS_OR_WORSE_COLUMN: share,
    }


def _build_region_phases(season_count: int) -> pd.DataFrame:
    """An August report before each season and a February report after it. The share of
    the near-term projection in August rises by a tenth per year.
    """
    phases = []
    for index in range(season_count):
        year = FIRST_SEASON_YEAR + index
        phases += [
            _build_phase(f"{year}-08", "CS", f"{year}-08", f"{year}-08", 0.5),
            _build_phase(f"{year}-08", "ML1", f"{year}-08", f"{year}-09", index / 10),
            _build_phase(f"{year}-08", "ML2", f"{year}-10", f"{year + 1}-01", 0.5),
            _build_phase(
                f"{year + 1}-02",
                "ML1",
                f"{year + 1}-02",
                f"{year + 1}-05",
                SHARE_AFTER_SEASON,
            ),
        ]
    return pd.DataFrame(phases)


def _build_observed_seasons(season_count: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "season_year": range(FIRST_SEASON_YEAR, FIRST_SEASON_YEAR + season_count),
            get_observed_drought_column(DEFAULT_DROUGHT_DEFINITION): [True]
            + [False] * (season_count - 1),
        }
    )


def test_an_issue_month_uses_the_near_term_projection_of_the_latest_report() -> None:
    # Arrange
    season_count = FEWS_NET_MINIMUM_SEASON_COUNT

    # Act
    cases = build_issue_month_cases(
        _build_region_phases(season_count),
        _build_observed_seasons(season_count),
        SHORT_RAINS,
    )

    # Assert
    # The August report is too old from January; the February report from July.
    assert sorted(cases[OFFSET_COLUMN].unique()) == [-4, -3, -2, -1, 0, 2, 3, 4]
    before_season = cases.loc[cases[OFFSET_COLUMN] == -4].set_index("season_year")
    assert before_season["issue_month"].unique().tolist() == [8]
    assert before_season["share"].tolist() == [index / 10 for index in range(10)]
    assert before_season["is_drought"].tolist() == [True] + [False] * 9
    assert not before_season.loc[FIRST_SEASON_YEAR, "is_alert"]
    assert before_season.loc[FIRST_SEASON_YEAR + season_count - 1, "is_alert"]
    after_season = cases.loc[cases[OFFSET_COLUMN] == 2]
    assert after_season["issue_month"].unique().tolist() == [2]
    assert after_season["share"].unique().tolist() == [SHARE_AFTER_SEASON]


def test_a_region_season_with_too_few_seasons_is_left_out() -> None:
    # Arrange
    season_count = FEWS_NET_MINIMUM_SEASON_COUNT - 1

    # Act
    cases = build_issue_month_cases(
        _build_region_phases(season_count),
        _build_observed_seasons(season_count),
        SHORT_RAINS,
    )

    # Assert
    assert cases.empty
