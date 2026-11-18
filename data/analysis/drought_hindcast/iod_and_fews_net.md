# IOD and FEWS NET

The two other indicators of spike AB#45772 (tasks AB#45805 and AB#45804): data collection and analysis. Their data locations are in `indicator_data.py`, their definitions in `indicator_definitions.py`, and the scores and chart parts that both share in `indicator_scoring.py` and `indicator_charts.py`. How to rerun everything and how to add a country is in the [README](./README.md).

## Data

| Data                          | Source                                                                                                      | Period                              | Script              |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------- | ----------------------------------- | ------------------- |
| Observed IOD index, 4 sources | NOAA PSL (HadISST), NOAA CPC (ERSST), NOAA OOPC (OISST, weekly), JAMSTEC (OISST); URLs in `download_iod.py` | 1981-01 to the latest month         | `download_iod`      |
| FEWS NET classifications      | [FEWS NET Data Warehouse](https://fdw.fews.net/data-explorer/) API, per classified unit                     | Reports of 2011-01 to latest report | `download_fews_net` |

Raw files land in `data/data/drought_hindcast/iod/` and `fews_net/`, the prepared tables in `intermediate/`.

## Run

`run_all` runs these steps with the SEAS5 analysis, in the order of `run_all.py` (see the [README](./README.md#reproduce-the-results)). On their own, from `data/`: `uv run python -m analysis.drought_hindcast.<step>`.

| Part              | Steps, in order                                                                                                                                                            |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Data              | `download_iod`, `download_fews_net`, `prepare_iod`, `prepare_fews_net`                                                                                                     |
| IOD analysis      | `calculate_iod_alerts`, `calculate_iod_skill`, `combine_indicators`, `plot_iod`                                                                                            |
| FEWS NET analysis | `calculate_fews_net_alerts`, `calculate_fews_net_skill`, `check_fews_net`, `compare_outcomes`, `plot_fews_net`, `check_kenya_region`, `compare_fews_net_with_skill_review` |

- No account is needed. Both downloads take less than five minutes.
- `download_iod` replaces its four files on every run. `download_fews_net` skips the years that were downloaded more than 90 days after their end.
- `prepare_fews_net` needs the region shapes of `build_region_shapes`.
- Both analyses need `calculate_alerts` and `calculate_skill` of the SEAS5 analysis.
- `check_kenya_region` needs the seed-data repo and the CHIRPS files, and takes about a minute.

## IOD

`prepare_iod` writes `intermediate/iod_monthly.csv`: one row per month, one column per source with the Dipole Mode Index in °C (sea surface temperature anomaly of the western box minus the eastern box). The weekly source is averaged over the weeks that start in a month; a month with fewer than four weeks is left out.

The source is still to choose. What the data shows, as downloaded on 2026-11-16:

| Column              | Latest month | Correlation with `iod_hadisst` | Standard deviation |
| ------------------- | ------------ | ------------------------------ | ------------------ |
| `iod_hadisst`       | 2026-05      | 1.00                           | 0.34               |
| `iod_ersst`         | 2026-08      | 0.90                           | 0.37               |
| `iod_oisst_weekly`  | 2026-09      | 0.80                           | 0.46               |
| `iod_oisst_jamstec` | 2026-10      | 0.80                           | 0.46               |

- The alert rule uses the previous month's index, so a source has to publish within a month. Only JAMSTEC did at the time of download.
- The two OISST series agree with each other (correlation 0.96) and vary more than the other two, so a threshold in °C does not carry over between sources.
- The first three average zero over 1991-2020, their base period. JAMSTEC averages 0.07 over those years, so it uses another base period.
- JAMSTEC starts in 1982-01 and the weekly series in 1981-09; the other two cover 1981 in full.
- The Australian Bureau of Meteorology index is not included: its server refuses scripted downloads.
- The JAMSTEC file also holds the SINTEX-F forecasts of the index, which are not used.

## IOD analysis

Definitions, all set in `indicator_definitions.py`:

- **Region-seasons:** a negative IOD goes with drought in ETH Southern OND and KEN National OND, a positive IOD with drought in Zimbabwe (Oct-Mar, OND and JFM).
- **Index of a run:** the average index over the months before the run month. One month is the proposed rule; four months at the October run is the setup of the Zimbabwe drought trigger (June to September, against JFM rainfall). It assumes that last month's index is known at the run.
- **Alert, own tercile (main rule):** the index is in the outer third of its own values for that run month in the other years, towards the phase that goes with drought. It alerts in a third of the years, which makes sources comparable.
- **Alert, fixed threshold:** the index is beyond 0.4 °C towards that phase.
- **Main source:** `oisst_weekly`, to be revisited. Every table holds all four.

Tables in `results/`:

- `iod_alerts.csv`: one row per region-season, season year, run month, source and number of index months, with the index, both alerts and the observed outcome. It also has the seasons that are not observed yet.
- `iod_skill_by_lead_time.csv`: the scores of `skill_by_lead_time.csv` for the IOD alerts, plus the ROC area of the index and its correlation with observed rainfall, with and without linear trends. `roc_area_for_wet_seasons` is the ROC area of the opposite phase for the wettest third of seasons. The pooled scope holds ETH Southern OND, KEN National OND and ZWE National Oct-Mar.
- `indicator_cases.csv`: one row per season and lead time that has both a SEAS5 forecast and an IOD index (main source, one month), with every alert below.
- `indicator_combinations.csv`: the scores of each of these alerts, per region-season and lead time:
  - `seas5` (at least 40% of members dry) and `iod` on their own;
  - `either` and `both`;
  - `all_with_skill`: every indicator that has skill for that region-season and lead time must alert. Skill is the skill review's bar for Include, a ROC area of at least 0.6 that is unlikely by chance. It is measured on the same years as it is scored on, which flatters it;
  - `seas5_at_lower_threshold` (30%) and `seas5_at_higher_threshold` (50%): a combination also changes how often there is an alert, so `either` and `both` are to be read against SEAS5 alone at a threshold that alerts about as often.
- `indicator_reliable_lead_times.csv`: per region-season and alert, the earliest forecast from which the alerts beat chance at every later forecast too, as in `reliable_lead_times.csv`.

`plot_iod` draws into `results/charts/`:

- `iod_roc_area`: the ROC area of SEAS5 against the index of every source, per region-season; a filled marker passes the skill review's bar. `iod_roc_area_short_rains` and `iod_roc_area_zimbabwe` show the same per group.
- `iod_skill_by_region_season`: hit rate and false-alarm ratio of the IOD alert.
- `indicator_combinations`: both measures per lead time for every alert above.
- `indicator_trade_off`: hit rate against false-alarm ratio, for SEAS5 alone at its three thresholds and for the alerts that use IOD, one month before the season and at its start.

In `results/drought_hindcast_slides.md`, section 6 (other indicators), the IOD slide of the Zimbabwe deep dive, the Kenya slide on the arid and semi-arid counties and the IOD and FEWS NET slides of the appendix are built on these charts and tables. Their texts and tables are written by hand, so check them after the numbers change. The Zimbabwe table takes the four-month index from `iod_skill_by_lead_time.csv` (`index_month_count` 4). The PDF is exported with the Marp extension of VS Code.

## FEWS NET

`download_fews_net` stores, per country:

- `classifications/<country>_<year>.csv.gz`: the phase of every unit in every report and scenario, for the periods that end in that year.
- `geographic_units/<country>_<unit type>.json`: name, area and centre of every unit. It has no shapes; these are roughly 100 kB per unit.

`prepare_fews_net` writes `intermediate/fews_net_region_phases.csv`: one row per region, report and scenario, with the share of the classified area in each phase and in Phase 3 or worse.

- **Scenario:** `CS` is the current situation in the report month, `ML1` the near-term projection and `ML2` the medium-term projection after it, each of up to four months. `projection_start` and `projection_end` give the months.
- **Region:** a unit counts towards the region that holds its centre. In a rough check, the area of the units of a region adds up to within about 2% of the area of the region.
- **Area:** shares are of the area that has a phase. National parks in Zimbabwe have none.
- **Left out:** camps for displaced people, the flag that a phase would be worse without assistance, and the highest phase in the country from the Food Assistance Outlook Brief (from 2023-04).

Coverage, as downloaded on 2026-11-16:

- Ethiopia, Kenya and Zimbabwe have reports from 2011: three or four a year up to 2018, each with all three scenarios. From 2019-2020 the projections are updated every month, the current situation three times a year.
- There are no reports between the end of 2024 and August to October 2025.
- Lesotho has reports from 2020-10 to 2024-10 and from 2026-06. Up to 2024 they are projections for the country as one unit, so the share is 0 or 1.
- The units change over time: Ethiopia has several versions of them, and Kenya and Zimbabwe moved from administrative areas to administrative areas split by livelihood zone. Every report covers the whole country once.
- The warehouse has nothing before 2011. The regional shapefiles on `shapefiles.fews.net` go back to 2009-07, but stop at 2021-09 and hold one shape per phase instead of units.

## FEWS NET analysis

Definitions, all set in `indicator_definitions.py`:

- **Value of a run:** the share of the region in Phase 3 or worse in the latest report from at least one month before the run month, and at most six. Recent reports reach the warehouse five to six weeks after the first of their month; a lag of two months is scored as well.
- **Projection:** of that report, the projection that covers most months of the season; with as many months, the earlier one; without any, the one that reaches furthest. `projection_season_month_count` tells how many season months it covers, which is often none four months before the season. Before the season it is the medium-term projection in nearly all cases.
- **Alert, own tercile (main rule):** the share is in the upper third of the region's own shares for that run month in the other years, and above zero. Phase 3 is the usual state of some regions, so a fixed share alerts almost every year there.
- **Alert, fixed share:** at least 20% of the region.
- **Alert, worsening:** the projected share is above the latest current situation, by an amount in the upper third of the region's own changes for that run month. The usual change differs per run month, as food insecurity follows the seasons.
- **Ranks:** the share and the change are also given as a rank among the other years of the region-season (0.5 is its usual level), so that regions can be pooled.
- **Not scored:** Lesotho, with four to six seasons.

Tables in `results/`:

- `fews_net_alerts.csv`: one row per region-season, season year, run month and report lag, with the report and projection used, the share, the alerts and the observed outcome.
- `fews_net_skill_by_lead_time.csv`: the scores of `skill_by_lead_time.csv`, per lead time, for SEAS5 on the same seasons (from 2011), for each FEWS NET rule, and for the main rule together with SEAS5 (`either`, `both`). The ROC area of a FEWS NET rule is that of the rank behind it. The pooled scope holds the pooled region-seasons except Lesotho.
- `fews_net_projection_check.csv`: FEWS NET against itself. Each medium-term projection is paired with the current situation that was classified within its period, and set next to assuming that the current situation at the report stays as it is. A near-term projection ends before the next current situation, so it has no pairs.
- `fews_net_after_season.csv`: per region-season, the share in the current situations of the six months after a season and its change from the latest current situation before the season, for drought seasons and other seasons, with the ROC area of each.
- `fews_net_season_outcomes.csv`: the seasons behind that table. `is_followed_by_impact` marks an impact season: the share rises, by an amount in the upper third of the rises of the region-season.
- `outcome_skill_by_lead_time.csv`, from `compare_outcomes`: the SEAS5 alerts scored against three outcomes on the same seasons: a dry season, an impact season, and a dry season that is also an impact season. It tests the outcome that the analysis is scored on, not an indicator. The false-alarm ratio moves with how many seasons count as an event, so read it next to `drought_frequency`.
- `kenya_region_check.csv`, from `check_kenya_region`: the observed MAM and OND rainfall of Kenya, its rank and whether it is a drought, for the whole country, for the 23 arid and semi-arid counties and for the 9 arid counties. CHIRPS only: SEAS5 is not rerun on those counties.
- `fews_net_around_season_end.csv`: month by month from three months before the end of a season to six months after it, the share in the near-term projection of the latest report against the usual share of the region, for drought seasons and other seasons, with its ROC area.
- `skill_review_fews_net_comparison.csv`, from `compare_fews_net_with_skill_review`: per region-season and issue month, the grade that the skill review gives FEWS NET next to what is measured here. The grades are copied from the sheet "Food-security decisions" of the review workbook into `inputs/skill_review_fews_net_grades.csv`. The review grades a month Include when its near-term projection reaches the impact window, the last two months of the season to three months after. So here the near-term projection of the latest report up to the issue month is scored on rainfall droughts with the own-tercile alert. Issue months run from five months before the last month of the season to four months after. It also draws the chart `skill_review_fews_net_comparison`.
- `skill_review_fews_net_pooled.csv`: the same scores per issue month for the ten region-seasons together.

`plot_fews_net` draws into `results/charts/`: `fews_net_shares_by_region` (the classifications over time, with the observed drought seasons), `fews_net_skill` (hit rate and false-alarm ratio per lead time, next to SEAS5) and `fews_net_around_season_end`.

Limits: the later current situation is classified by the same analysts as the projection, so the projection check is not an independent test. Projected changes include the usual seasonal change, which is easy to get right.
