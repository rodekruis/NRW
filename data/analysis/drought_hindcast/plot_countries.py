"""Per country: the skill of each of its region-seasons ordered by season, the cases
behind it, and the lead time from which its alerts can be relied on."""

import pandas as pd
from analysis.drought_hindcast.calculate_skill import (
    CHANCE_SIGNIFICANCE_LEVEL,
    load_scorable_cases,
)
from analysis.drought_hindcast.check_skill import add_outcomes, plot_cases_by_year
from analysis.drought_hindcast.definitions import REGION_SEASONS, RegionSeason
from analysis.drought_hindcast.plot_skill import (
    DEFAULT_DROUGHT_DEFINITION,
    DEFAULT_RULE,
    plot_region_seasons,
    select_scores,
)
from analysis.drought_hindcast.study_area import RELIABLE_LEAD_TIMES_FILE, SKILL_FILE

# Order of the seasons in the charts; a whole rainy season comes before its halves.
SEASON_ORDER = ("MAM", "JAS", "Oct-Mar", "OND", "JFM")
SEASONS_PER_CHART_ROW = 3
MONTHS_PER_YEAR = 12
RAINY_SEASON_YEAR_AXIS_LABEL = (
    "Year in which the rainy season starts (a season after the new year is shown "
    "with the October before it)"
)


def main() -> None:
    skill = pd.read_csv(SKILL_FILE)
    cases = add_outcomes(load_scorable_cases())
    for country_code_iso3, region_seasons in _group_by_country().items():
        file_suffix = country_code_iso3.lower()
        plot_region_seasons(
            skill,
            region_seasons,
            DEFAULT_RULE,
            min(len(region_seasons), SEASONS_PER_CHART_ROW),
            f"skill_{file_suffix}",
        )
        _plot_cases(cases, region_seasons, f"cases_{file_suffix}")
    _write_reliable_lead_times(skill)


def _group_by_country() -> dict[str, list[RegionSeason]]:
    """The region-seasons of each country, ordered by season."""
    countries: dict[str, list[RegionSeason]] = {}
    for region_season in sorted(
        REGION_SEASONS,
        key=lambda region_season: SEASON_ORDER.index(region_season.season_name),
    ):
        countries.setdefault(region_season.country_code_iso3, []).append(region_season)
    return {
        country_code_iso3: countries[country_code_iso3]
        for country_code_iso3 in dict.fromkeys(
            region_season.country_code_iso3 for region_season in REGION_SEASONS
        )
    }


def _plot_cases(
    cases: pd.DataFrame, region_seasons: list[RegionSeason], file_name: str
) -> None:
    """The cases by year, with every season in the column of its rainy season."""
    years_after_rainy_season_start = {
        region_season.name: count_years_after_rainy_season_start(
            region_season, region_seasons
        )
        for region_season in region_seasons
    }
    names = list(years_after_rainy_season_start)
    if not any(years_after_rainy_season_start.values()):
        plot_cases_by_year(cases, names, file_name)
        return
    plot_cases_by_year(
        cases.assign(
            season_year=cases["season_year"]
            - cases["region_season"].map(years_after_rainy_season_start).fillna(0)
        ).astype({"season_year": int}),
        names,
        file_name,
        year_axis_label=RAINY_SEASON_YEAR_AXIS_LABEL,
    )


def count_years_after_rainy_season_start(
    region_season: RegionSeason, region_seasons: list[RegionSeason]
) -> int:
    """1 for a season that starts in the calendar year after its rainy season started.

    The rainy season is the pooled season of the same region that holds its first month.
    """
    first_month = region_season.months[0]
    for rainy_season in region_seasons:
        if (
            rainy_season.is_in_pooled_results
            and rainy_season.region_key == region_season.region_key
            and first_month in rainy_season.months
        ):
            return int(first_month < rainy_season.months[0])
    return 0


def _write_reliable_lead_times(skill: pd.DataFrame) -> None:
    """Per region-season, the earliest forecast from which the alerts beat chance."""
    rows = []
    for region_season in REGION_SEASONS:
        scores = select_scores(
            skill, region_season.name, DEFAULT_RULE, DEFAULT_DROUGHT_DEFINITION
        ).set_index("months_until_season_start")
        reliable_from = get_first_reliable_lead_time(
            (scores["probability_by_chance"] < CHANCE_SIGNIFICANCE_LEVEL).to_dict()
        )
        # Without a reliable lead time, the scores at the season start are given.
        scores_shown = scores.loc[reliable_from if reliable_from is not None else 0]
        rows.append(
            {
                "region_season": region_season.name,
                "is_in_pooled_results": region_season.is_in_pooled_results,
                "reliable_from_months_before_season": reliable_from,
                "reliable_from_run_month": (
                    None
                    if reliable_from is None
                    else _get_run_month(region_season, reliable_from)
                ),
                "hit_rate": scores_shown["hit_rate"],
                "false_alarm_ratio": scores_shown["false_alarm_ratio"],
                "drought_count": int(scores_shown["drought_count"]),
            }
        )
    reliable_lead_times = pd.DataFrame(rows).astype(
        {
            "reliable_from_months_before_season": "Int64",
            "reliable_from_run_month": "Int64",
        }
    )
    reliable_lead_times.to_csv(RELIABLE_LEAD_TIMES_FILE, index=False)
    print(f"Wrote {len(reliable_lead_times)} rows to {RELIABLE_LEAD_TIMES_FILE}")
    print(reliable_lead_times.to_string(index=False))


def get_first_reliable_lead_time(
    beats_chance_by_lead_time: dict[int, bool],
) -> int | None:
    """Longest lead time from which the alerts beat chance at every later forecast too.

    A forecast that beats chance while a later one does not is taken to be luck.
    """
    reliable_from = None
    for months_before_season in sorted(beats_chance_by_lead_time):
        if not beats_chance_by_lead_time[months_before_season]:
            break
        reliable_from = months_before_season
    return reliable_from


def _get_run_month(region_season: RegionSeason, months_before_season: int) -> int:
    return (region_season.months[0] - months_before_season - 1) % MONTHS_PER_YEAR + 1


if __name__ == "__main__":
    main()
