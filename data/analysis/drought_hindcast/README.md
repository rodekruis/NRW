# Drought hindcast analysis

Spike AB#45772: measure on historical data how well the proposed drought alert logic works, to validate the skill review and calibrate thresholds.

This README covers how to rerun and extend the analysis, and the SEAS5 part of it: data collection, the calculation and the alert rule, skill charts, and comparisons with the earlier 2025-26 matrix and with the skill review. IOD and FEWS NET as further indicators are in [iod_and_fews_net.md](./iod_and_fews_net.md).

| Where                                        | What                                                                    |
| -------------------------------------------- | ----------------------------------------------------------------------- |
| `definitions.py`, `indicator_definitions.py` | The region-seasons, the alert rules and thresholds, the drought measure |
| `run_all.py`                                 | Every step, in the order in which they depend on each other             |
| `inputs/`                                    | Tables copied by hand from the skill review and the earlier matrix      |
| `results/`                                   | The result tables, `charts/`, and the two slide decks                   |
| `data/data/drought_hindcast/` (git-ignored)  | Region shapes, downloaded data and intermediate files, about 1 GB       |

## Reproduce the results

1. Set up the Python environment of `data/` as in the [data README](../../README.md#prerequisites): Python, uv, GDAL and ecCodes, then `./uv-sync.sh`.
2. Clone the seed-data repo and point `SEED_DATA_REPO_ROOT` in `data/.env` to it. It holds the admin areas that the region shapes are built from.
3. Get a Copernicus CDS account for SEAS5: accept the dataset's licence on its [download page](https://cds.climate.copernicus.eu/datasets/seasonal-monthly-single-levels?tab=download), then put your personal access token in `CDSAPI_KEY` in `data/.env`, or in `~/.cdsapirc`. The other sources need no account.
4. From `data/`:

```bash
uv run python -m analysis.drought_hindcast.run_all --collect-data
uv run pytest analysis/
```

- **`--collect-data`** builds the region shapes and downloads all data first. CHIRPS takes about half an hour (its server limits the speed), SEAS5 about an hour, IOD and FEWS NET a few minutes. The CHIRPS, SEAS5 and FEWS NET downloads skip what is already there, so the command can be rerun to resume.
- **Without it,** `run_all` runs every step from the downloaded data to the tables and charts, in about four minutes. Every step rebuilds its output from scratch.
- **One step:** `uv run python -m analysis.drought_hindcast.<step>`. To resume a run: `run_all --from-step <step>`. The steps and their order are in `run_all.py`.
- **Run from `data/`.** The region shapes read the alert configuration of the api-service by a path relative to it.
- **The slide decks** are written by hand on the tables and charts. Export them to PDF with [Marp](https://marp.app), for example with its VS Code extension.

From the same downloaded data, a rerun gives the same tables and charts, byte for byte. That was checked on 18 November 2026, for all 24 tables and 42 charts. The uncertainty ranges are drawn with a fixed seed.

### The data behind the committed results

The sources are live, so a download at a later date holds more months, and the numbers move with them. The committed results were made with:

| Data              | State                                                                         | Downloaded       |
| ----------------- | ----------------------------------------------------------------------------- | ---------------- |
| Seed-data repo    | Revision `3639e28`                                                            | 13 November 2026 |
| CHIRPS v3.0 final | 1981-01 to 2026-09, 550 months                                                | 13 November 2026 |
| SEAS5 system 51   | Start months 1981-01 to 2026-11                                               | 13 November 2026 |
| IOD, four sources | Latest month per source between 2026-05 and 2026-10; these series get revised | 16 November 2026 |
| FEWS NET          | Reports of 2011 to 2026                                                       | 16 November 2026 |

`download_iod` replaces its files on every run, and `download_fews_net` refreshes the recent years. To reproduce the committed numbers exactly, use a copy of the data folder of that date instead of `--collect-data`.

## Add a country, a region or a season

Steps 1 to 3 were tried on 18 November 2026 with Uganda (Karamoja April to October, Central MAM and SON). The alerts, the scores, the reliable lead times and the charts per country and per region-season then included it. Steps 4 to 6 follow from the code and were not run for a new country.

1. **Country:** add its ISO3 code to `STUDY_COUNTRIES` in `build_region_shapes.py`. Its admin areas must be in the seed-data repo. A country with drought regions in `seed-alert-configs.const.ts` gets those regions; any other country becomes one region, `National`.
2. **Region-seasons:** add a `RegionSeason` per region and season to `REGION_SEASONS` in `definitions.py`: the country code, the region name as in the region shapes, a season name, and the season's months in order. Give an extra season definition of a region that is already counted `is_in_pooled_results=False`.
3. **Run** `build_region_shapes`, then `run_all`. All data is cut to one box around all regions. If the new region lies outside it, `prepare_observed_rainfall` stops and says so: delete the `chirps` and `seas5` folders and run `run_all --collect-data`.
4. **IOD, if it applies:** add the region-season and the phase that goes with drought to `IOD_DROUGHT_PHASES` in `indicator_definitions.py`.
5. **FEWS NET, if it reports on the country:** add its two-letter code to `FEWS_NET_COUNTRY_CODES` in `download_fews_net.py` and run `download_fews_net` again.
6. **Skill review:** add the review's grades to `inputs/skill_review_seas5_grades.csv` and `inputs/skill_review_fews_net_grades.csv`. Without them the region-season is left out of those two comparisons.

What to expect:

- **The results for all region-seasons together change,** as the new ones count towards them. The scores of the existing region-seasons stay the same. Their uncertainty ranges can move a little for those listed after the new ones, as all ranges are drawn from one random sequence.
- **A season of more than six months** is never forecast whole: SEAS5 reaches six months. The charts mark such forecasts as "part of season".
- **Not generic:** `check_kenya_region`, the short-rains charts of `plot_threshold_choices`, the example of `plot_alert_rules` and the comparison with the earlier matrix are about specific regions. The two slide decks are written by hand.

## Data

| Data                              | Source                                                                                                                      | Period                                 | Script                |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- | --------------------- |
| Region shapes (7 regions)         | Seed-data admin areas, grouped by the place codes in `seed-alert-configs.const.ts`                                          | -                                      | `build_region_shapes` |
| Observed monthly rainfall         | [CHIRPS v3.0](https://data.chc.ucsb.edu/products/CHIRPS/v3.0/) monthly, final product, 0.05°                                | 1981-01 to latest final month          | `download_chirps`     |
| Forecast monthly rainfall (SEAS5) | [Copernicus CDS](https://cds.climate.copernicus.eu/datasets/seasonal-monthly-single-levels), ECMWF system 51, 1°, leads 1-6 | Start months 1981-01 to latest release | `download_seas5`      |

The regions are the four Ethiopian climate regions (Belg, Meher, Northern, Southern) and Kenya, Zimbabwe and Lesotho as a whole. CHIRPS and SEAS5 are both cut to one whole-degree box around all regions (24°E-49°E, 32°S-16°N).

## Calculation

`prepare_observed_rainfall` averages CHIRPS over each region per month. `prepare_forecast_rainfall` converts SEAS5 to mm per month and keeps the grid cells that overlap a region. Region averages weight each cell by the share of it inside the region and by its area.

`calculate_alerts` then works per region-season (15, listed in `definitions.py`), season year (the year of the season's first month) and run month, and writes two tables:

- `results/observed_seasons.csv`: observed season rainfall, and whether the season is in the driest third or fifth of years.
- `results/forecast_alerts.csv`: one row per run month and variant, with the forecast, its reference values, the alerts and the observed outcome.

Definitions, all set in `definitions.py`:

- **Run months:** from 4 months before the season to its last month (`months_until_season_start` from 4 down to negative values within the season).
- **Forecast value:** per member, the region-average rainfall summed over the season months that the run can see. SEAS5 reaches 6 months, so early runs miss the end of the season; `forecast_month_count` shows how many months are included.
- **Reference:** the same value for the same run month in the hindcast years (up to 2016, 25 members), leaving out the year itself.
- **Alert (region-average rule):** the share of members below the lower tercile of the reference is at least 0.3, 0.4, 0.5 or 0.6. Results are reported for 0.4 unless stated otherwise. This is the rule proposed in the spike. In the tables it is `probability_0.3` to `probability_0.6`.
- **Grid-cell rule (IBF v1):** `area_rule` in the code and tables. Per grid cell, the share of members below that cell's own lower tercile; alert when cells with a share of at least 0.4 cover at least 40% of the region.
- **Pooled results:** Zimbabwe and Lesotho are scored on three season definitions: the whole rainy season (Oct-Mar) and its two halves (OND, JFM). Only Oct-Mar counts towards results for all region-seasons together, so that each country counts once: 11 region-seasons.
- **Variants within the season:** `rest_of_season` uses the remaining months only; `earlier_forecast_for_past_months` adds each past month from the forecast that started in that month; `observed_for_past_months` adds the observed rainfall of the past months.

## Skill charts

`calculate_skill` counts hits and false alarms in `results/forecast_alerts.csv` for runs up to the season start, and writes `results/skill_by_lead_time.csv`: hit rate and false-alarm ratio per lead time, alert rule, drought definition and region-season (plus the 11 pooled region-seasons together). The uncertainty ranges come from resampling whole years, because region-seasons in the same year are not independent.

Per region-season, `probability_by_chance` is the probability of at least as many hits if the same number of alerts were spread at random over the seasons (one-sided Fisher exact test). `calculate_skill` prints how many region-seasons stay below 5%.

`plot_skill` draws the same chart in several breakdowns into `results/charts/`. `plot_alert_rules` draws one forecast under the region-average rule and under the grid-cell rule, and prints how often the two agree. `plot_thresholds` sweeps the share of members that must be dry from 30% to 70% and draws both measures against it, for three lead times.

`plot_threshold_steps` splits the forecasts of the pooled region-seasons, per lead time, by the highest alert threshold they reach: 60% or more, 50-60%, 40-50%, 30-40% and below 30%. `results/threshold_steps.csv` gives per band the forecasts, how many were not followed by a drought, and that false-alarm ratio next to the ratio of alerts unrelated to droughts. A band is what one step down in the threshold adds, so its ratio shows whether those added alerts are better than random ones. The chart `threshold_steps` shows it one month before the season and at its start.

`plot_threshold_choices` shows what the threshold changes per region-season. It gives every combination of region-season, threshold and lead time one of three evidence levels, as `rule_level` in the comparison with the skill review: the alerts beat chance, the hit rate is above the level without skill but could be luck, or neither.

- `results/threshold_choices.csv`: per region-season and threshold, the longest lead time from which the alerts beat chance at that forecast and every later one (`alert_from_months_before_season`), and the longest from which the hit rate stays above the level without skill (`advisory_from_months_before_season`), with the scores at the first of these, or else at the season start.
- The chart `evidence_by_threshold` shows the hit rate and false-alarm ratio per region-season and lead time, one grid per threshold, coloured by evidence level. `evidence_at_default_threshold` is the grid of the 40% rule on its own, for the summary deck: region-seasons ordered from the earliest reliable alert, and the legend in that deck's words.
- The charts `skill_short_rains_by_threshold` and `cases_short_rains_by_threshold` show the two OND region-seasons of East Africa at each threshold: both measures per lead time, and the years behind them one month before the season.

`plot_in_season` scores the forecasts issued within the season, for each way to account for the season months that have passed (the variants above). `results/skill_in_season.csv` holds the scores of the 40% rule per variant and lead time, down to the last season month, for all region-seasons together and per region-season; up to the season start the variants are the same forecast. Within the season `full_season_share` counts the past months as covered for the two variants that fill them in. The chart `skill_in_season` shows all region-seasons together from four months before the season to two months into it.

`plot_countries` draws, per country, the skill of each region-season ordered by season (for Zimbabwe and Lesotho all three season definitions) and the cases behind it. In the cases chart a season after the new year sits in the column of the rainy season it belongs to, so JFM 2024 is shown with Oct-Mar 2023. It also writes `results/reliable_lead_times.csv`: per region-season, the longest lead time from which the alerts of the 40% rule beat chance at that forecast and at every later one, with the scores at that forecast.

`results/drought_hindcast_slides.md` is a [Marp](https://marp.app) slide deck built on the charts, for SEAS5, IOD and FEWS NET together; the takeaway texts and tables in it are written by hand, so check them after the numbers change. `results/drought_hindcast_summary.md` is a second, short deck for product decisions: the preliminary conclusions, the choices that are open and who makes them, and one slide per country. It takes its numbers from the first deck, so change the two together. Four charts are drawn but not in the first deck: `skill_by_threshold`, `skill_with_shuffled_years`, `indicator_combinations` and `iod_skill_by_region_season`.

## Comparisons

`compare_with_earlier_matrix` relates this analysis to the earlier 2x2 matrix of IBF v1 alerts against reported droughts in 2025-26 (the workbook `Drought_events_vs_IBF_alerts_ETH_KEN_LSO.xlsx`, sheet Matrix).

- `inputs/earlier_matrix_cells.csv` holds the 24 counted cells of that matrix, copied by hand, each with the region-season and season year it maps to here. The mapping is a judgement: two Belg areas share one forecast, Kenya ASAL maps to the whole country, and the Kenya JAS cells have no forecast.
- `results/earlier_matrix_cases.csv` adds to each cell whether each rule alerts, one month before the season or at any of the five forecasts before it, the outcome against the reported drought, and the observed rainfall with its rank. `counts_once` marks the first cell of each forecast, for scoring against observed droughts.
- The charts `matrix_*` show the 2x2 matrix step by step: the earlier matrix, our closest version of it (grid-cell rule, an alert at any lead time) with one change at a time, an alert at any lead time against one month before, the region-average rule one month before from the 24 cells to all years, and all years at each threshold. The hit rate and the false-alarm ratio are written in the cells.
- It also prints in how many cells each version has an alert where the earlier matrix has one.

`compare_with_skill_review` relates it to the SEAS5 grades of the skill review (`NRW_drought_indicator_skill_IFRC_Africa.xlsx`, sheet Climate decisions).

- `inputs/skill_review_seas5_grades.csv` holds the grade (Include, Readiness, Exclude) per pooled region-season and issue month, copied by hand, with the workbook's decision id. Kenya takes the grades of the ASAL zones.
- `results/skill_review_comparison.csv` adds what is measured here: the scores of the 40% rule, the ROC area for the driest third (the chance that a drought year had a larger share of dry members than another year), its probability by chance, and the correlation of the ensemble mean with observed rainfall.
- `rule_level` says how far the alerts of the 40% rule stand out: Include where their hits are unlikely by chance, Readiness where the hit rate is above the level without skill. `roc_level` applies the review's own bar to the forecast: Include at a ROC area of at least 0.6 that is unlikely by chance, Readiness above 0.5.
- The chart `skill_review_comparison` shows the grades next to the hit rate and false-alarm ratio of the 40% rule, as a grid of region-season by lead time, coloured by `rule_level`. A dot marks where the forecast passes the review's bar.

## Checks

`check_against_raw_data` recalculates the observed seasons and the pre-season forecasts from the raw files along a separate route, and prints how far they are from the result tables. It shares the definitions with `calculate_alerts` but not its code: it cuts out regions by exact overlap, and averages over the region before adding up the months. It takes about two minutes. It does not cover the grid-cell rule or the runs within the season.

`check_skill` draws three charts and prints the numbers behind them:

- `cases_by_year`: every scored season of the 11 pooled region-seasons, marked as hit, miss, false alarm or neither.
- `skill_with_shuffled_years`: the scores against what is left of them when the alerts are scored against the droughts of other years. Whole years are shuffled, so that region-seasons keep the droughts they share.
- `skill_by_period`: the scores for both halves of the period, and for hindcast and forecast years.

It also prints how many independent droughts the sample is worth, how many alerts depend on a single member, and the correlation between forecast and observed rainfall with and without linear trends.

## Source notes

- CHIRPS v2.0 is still published alongside v3.0, with the same period. v3.0 uses about four times as many station sources and corrects for gauge undercatch, which makes it wetter overall.
- SEAS5 system 51 is the only ECMWF system on the CDS that covers the whole period; system 5 ends at start month 2022-10. It has 25 members for start months up to 2016-12 and 51 from 2017-01.
- IBF v1 does not keep SEAS5 hindcasts in storage: it requests them from the CDS on every run (`droughtpipeline/load.py` in `rodekruis/IBF-drought-pipeline`).
