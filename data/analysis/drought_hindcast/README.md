# Drought hindcast analysis

Spike AB#45772: measure on historical data how well the proposed drought alert logic works, to validate the skill review and calibrate thresholds.

This README covers SEAS5: data collection, the calculation and the alert rule, skill charts, and comparisons with the earlier 2025-26 matrix and with the skill review. IOD and FEWS NET as further indicators are in [iod_and_fews_net.md](./iod_and_fews_net.md). Raw and intermediate data land in `data/data/drought_hindcast/` (git-ignored); hand-made input tables are in `inputs/`; result tables in `results/`.

## Data

| Data                              | Source                                                                                                                      | Period                                 | Script                |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | -------------------------------------- | --------------------- |
| Region shapes (7 regions)         | Seed-data admin areas, grouped by the place codes in `seed-alert-configs.const.ts`                                          | -                                      | `build_region_shapes` |
| Observed monthly rainfall         | [CHIRPS v3.0](https://data.chc.ucsb.edu/products/CHIRPS/v3.0/) monthly, final product, 0.05°                                | 1981-01 to latest final month          | `download_chirps`     |
| Forecast monthly rainfall (SEAS5) | [Copernicus CDS](https://cds.climate.copernicus.eu/datasets/seasonal-monthly-single-levels), ECMWF system 51, 1°, leads 1-6 | Start months 1981-01 to latest release | `download_seas5`      |

The regions are the four Ethiopian climate regions (Belg, Meher, Northern, Southern) and Kenya, Zimbabwe and Lesotho as a whole. CHIRPS and SEAS5 are both cut to one whole-degree box around all regions (24°E-49°E, 32°S-16°N).

## Run

From `data/`, in this order (the downloads take their extent from the region shapes):

```bash
uv run python -m analysis.drought_hindcast.build_region_shapes
uv run python -m analysis.drought_hindcast.download_chirps
uv run python -m analysis.drought_hindcast.download_seas5
uv run python -m analysis.drought_hindcast.prepare_observed_rainfall
uv run python -m analysis.drought_hindcast.prepare_forecast_rainfall
uv run python -m analysis.drought_hindcast.calculate_alerts
uv run python -m analysis.drought_hindcast.calculate_skill
uv run python -m analysis.drought_hindcast.plot_skill
uv run python -m analysis.drought_hindcast.plot_alert_rules
uv run python -m analysis.drought_hindcast.plot_thresholds
uv run python -m analysis.drought_hindcast.plot_threshold_steps
uv run python -m analysis.drought_hindcast.check_skill
uv run python -m analysis.drought_hindcast.compare_with_earlier_matrix
uv run python -m analysis.drought_hindcast.compare_with_skill_review
uv run python -m analysis.drought_hindcast.plot_countries
uv run python -m analysis.drought_hindcast.check_against_raw_data
uv run pytest analysis/
```

- `build_region_shapes` needs a local clone of the seed-data repo (`SEED_DATA_REPO_ROOT` in `data/.env`).
- `download_seas5` needs a Copernicus CDS account: accept the dataset's licence on its CDS download page, then put your personal access token in `CDSAPI_KEY` in `data/.env`, or in `~/.cdsapirc`.
- Both downloads skip what is already there, so they can be rerun to resume or to pick up new months. The CHIRPS server limits download speed; the full record takes about half an hour, SEAS5 about an hour.
- The two `prepare_` scripts and `calculate_alerts` rebuild their output from scratch; together they take about a minute.

## Calculation

`prepare_observed_rainfall` averages CHIRPS over each region per month. `prepare_forecast_rainfall` converts SEAS5 to mm per month and keeps the grid cells that overlap a region. Region averages weight each cell by the share of it inside the region and by its area.

`calculate_alerts` then works per region-season (15, listed in `definitions.py`), season year (the year of the season's first month) and run month, and writes two tables:

- `results/observed_seasons.csv`: observed season rainfall, and whether the season is in the driest third or fifth of years.
- `results/forecast_alerts.csv`: one row per run month and variant, with the forecast, its reference values, the alerts and the observed outcome.

Definitions, all set in `definitions.py`:

- **Run months:** from 4 months before the season to its last month (`months_until_season_start` from 4 down to negative values within the season).
- **Forecast value:** per member, the region-average rainfall summed over the season months that the run can see. SEAS5 reaches 6 months, so early runs miss the end of the season; `forecast_month_count` shows how many months are included.
- **Reference:** the same value for the same run month in the hindcast years (up to 2016, 25 members), leaving out the year itself.
- **Alert (region rule):** the share of members below the lower tercile of the reference is at least 0.3, 0.4, 0.5 or 0.6. Results are reported for 0.4 unless stated otherwise. This is the rule proposed in the spike.
- **Area rule (IBF v1):** per grid cell, the share of members below that cell's own lower tercile; alert when cells with a share of at least 0.4 cover at least 40% of the region.
- **Pooled results:** Zimbabwe and Lesotho are scored on three season definitions: the whole rainy season (Oct-Mar) and its two halves (OND, JFM). Only Oct-Mar counts towards results for all region-seasons together, so that each country counts once: 11 region-seasons.
- **Variants within the season:** `rest_of_season` uses the remaining months only; `earlier_forecast_for_past_months` adds each past month from the forecast that started in that month; `observed_for_past_months` adds the observed rainfall of the past months.

## Skill charts

`calculate_skill` counts hits and false alarms in `results/forecast_alerts.csv` for runs up to the season start, and writes `results/skill_by_lead_time.csv`: hit rate and false-alarm ratio per lead time, alert rule, drought definition and region-season (plus the 11 pooled region-seasons together). The uncertainty ranges come from resampling whole years, because region-seasons in the same year are not independent.

Per region-season, `probability_by_chance` is the probability of at least as many hits if the same number of alerts were spread at random over the seasons (one-sided Fisher exact test). `calculate_skill` prints how many region-seasons stay below 5%.

`plot_skill` draws the same chart in several breakdowns into `results/charts/`. `plot_alert_rules` draws one forecast under the region rule and under the area rule, and prints how often the two agree. `plot_thresholds` sweeps the share of members that must be dry from 30% to 70% and draws both measures against it, for three lead times.

`plot_threshold_steps` splits the forecasts of the pooled region-seasons, per lead time, by the highest alert threshold they reach: 60% or more, 50-60%, 40-50%, 30-40% and below 30%. `results/threshold_steps.csv` gives per band the forecasts, how many were followed by a drought, and the share of all seasons with a drought. A band is what one step down in the threshold adds, so its share shows whether those added alerts are better than alerts unrelated to droughts. The chart `threshold_steps` shows it one month before the season and at its start.

`plot_countries` draws, per country, the skill of each region-season ordered by season (for Zimbabwe and Lesotho all three season definitions) and the cases behind it. In the cases chart a season after the new year sits in the column of the rainy season it belongs to, so JFM 2024 is shown with Oct-Mar 2023. It also writes `results/reliable_lead_times.csv`: per region-season, the longest lead time from which the alerts of the 40% rule beat chance at that forecast and at every later one, with the scores at that forecast.

`results/drought_hindcast_slides.md` is a [Marp](https://marp.app) slide deck built on the charts, for SEAS5, IOD and FEWS NET together; the takeaway texts and tables in it are written by hand, so check them after the numbers change. Four charts are drawn but not in the deck: `skill_by_threshold`, `skill_with_shuffled_years`, `indicator_combinations` and `iod_skill_by_region_season`.

## Comparisons

`compare_with_earlier_matrix` relates this analysis to the earlier 2x2 matrix of IBF v1 alerts against reported droughts in 2025-26 (the workbook `Drought_events_vs_IBF_alerts_ETH_KEN_LSO.xlsx`, sheet Matrix).

- `inputs/earlier_matrix_cells.csv` holds the 24 counted cells of that matrix, copied by hand, each with the region-season and season year it maps to here. The mapping is a judgement: two Belg areas share one forecast, Kenya ASAL maps to the whole country, and the Kenya JAS cells have no forecast.
- `results/earlier_matrix_cases.csv` adds to each cell whether each rule alerts, one month before the season or at any of the five forecasts before it, the outcome against the reported drought, and the observed rainfall with its rank. `counts_once` marks the first cell of each forecast, for scoring against observed droughts.
- The charts `matrix_*` show the 2x2 matrix step by step: the earlier matrix, our closest version of it (area rule, an alert at any lead time) with one change at a time, an alert at any lead time against one month before, the region rule one month before from the 24 cells to all years, and all years at each threshold. The hit rate and the false-alarm ratio are written in the cells.
- It also prints in how many cells each version has an alert where the earlier matrix has one.

`compare_with_skill_review` relates it to the SEAS5 grades of the skill review (`NRW_drought_indicator_skill_IFRC_Africa.xlsx`, sheet Climate decisions).

- `inputs/skill_review_seas5_grades.csv` holds the grade (Include, Readiness, Exclude) per pooled region-season and issue month, copied by hand, with the workbook's decision id. Kenya takes the grades of the ASAL zones.
- `results/skill_review_comparison.csv` adds what is measured here: the scores of the 40% rule, the ROC area for the driest third (the chance that a drought year had a larger share of dry members than another year), its probability by chance, and the correlation of the ensemble mean with observed rainfall.
- `rule_level` says how far the alerts of the 40% rule stand out: Include where their hits are unlikely by chance, Readiness where the hit rate is above the level without skill. `roc_level` applies the review's own bar to the forecast: Include at a ROC area of at least 0.6 that is unlikely by chance, Readiness above 0.5.
- The chart `skill_review_comparison` shows the grades next to the hit rate and false-alarm ratio of the 40% rule, as a grid of region-season by lead time, coloured by `rule_level`. A dot marks where the forecast passes the review's bar.

## Checks

`check_against_raw_data` recalculates the observed seasons and the pre-season forecasts from the raw files along a separate route, and prints how far they are from the result tables. It shares the definitions with `calculate_alerts` but not its code: it cuts out regions by exact overlap, and averages over the region before adding up the months. It takes about two minutes. It does not cover the area rule or the runs within the season.

`check_skill` draws three charts and prints the numbers behind them:

- `cases_by_year`: every scored season of the 11 pooled region-seasons, marked as hit, miss, false alarm or neither.
- `skill_with_shuffled_years`: the scores against what is left of them when the alerts are scored against the droughts of other years. Whole years are shuffled, so that region-seasons keep the droughts they share.
- `skill_by_period`: the scores for both halves of the period, and for hindcast and forecast years.

It also prints how many independent droughts the sample is worth, how many alerts depend on a single member, and the correlation between forecast and observed rainfall with and without linear trends.

## Source notes

- CHIRPS v2.0 is still published alongside v3.0, with the same period. v3.0 uses about four times as many station sources and corrects for gauge undercatch, which makes it wetter overall.
- SEAS5 system 51 is the only ECMWF system on the CDS that covers the whole period; system 5 ends at start month 2022-10. It has 25 members for start months up to 2016-12 and 51 from 2017-01.
- IBF v1 does not keep SEAS5 hindcasts in storage: it requests them from the CDS on every run (`droughtpipeline/load.py` in `rodekruis/IBF-drought-pipeline`).
