# One HydroBASINS area per GloFAS station

Analysis for spike AB#42674: replace the hand-made list of admin areas per GloFAS station with an area derived from river basins.

It starts from the rule of draft PR #99 (the largest HydroBASINS basin that contains the station and no other station), shows where that rule falls short, and measures variants of it. Nothing here is used by the pipelines.

## Inputs

- A local clone of the seed repo (`SEED_DATA_REPO_ROOT` in `data/.env`, or `--seed-repo-root`): the station thresholds with their admin areas, the admin areas, and the 10-year flood map in `hazard/flood/flood-extents/data-png/`.
- [HydroBASINS](https://www.hydrosheds.org/products/hydrobasins) v1.c, standard variant, for Africa and Australasia. The Philippines is in the Australasia file, not in the Asia file. The archives go in `data/data/hydrobasins/`, which is not tracked (or pass `--basins-dir`):

```bash
cd data
mkdir -p data/hydrobasins
curl --fail -o data/hydrobasins/hybas_af_lev01-12_v1c.zip https://data.hydrosheds.org/file/hydrobasins/standard/hybas_af_lev01-12_v1c.zip
curl --fail -o data/hydrobasins/hybas_au_lev01-12_v1c.zip https://data.hydrosheds.org/file/hydrobasins/standard/hybas_au_lev01-12_v1c.zip
```

## Scripts

- `initial_rule.py` applies the rule of PR #99 to all stations: a map per country, a summary per station and per country, the stations whose current footprint is in separate parts, and before-and-after figures against the flood map. It also runs the rule with the stations of all countries counted together.
- `rule_sensitivity.py` varies one choice of the rule at a time (start level, area cap, minimum area, which other stations count, lumped coastal units, whether a station must be alone, following the river downstream) and measures every variant on the same numbers. It draws a chart per choice and a comparison per country.

```bash
uv run python -m analysis.station_basins.initial_rule
uv run python -m analysis.station_basins.rule_sensitivity
```

Results are written to `results/`. Run `npm run fix:prettier` from the repo root afterwards; it formats the generated `results/summary.md`. Intermediate files that can be rebuilt go to `data/data/station_basins/`, and the extracted shapefiles next to the archives.

`results/station_basin_rule_slides.md` is a [Marp](https://marp.app) slide deck on the rule, the variants and a candidate. Its texts and tables are written by hand, so check them after the numbers change.

## State of the results

- The results use the seed repo at commit `3639e28`. NRW-seed-data PR #24 moves 17 stations to the centre of their river cell; the results do not include that move yet.
- "Outside the country" counts lake surface as outside, also for lakes inside a country.
- Not analysed yet: stopping the downstream trace at a large confluence instead of at a fixed distance, clipping the areas to the country, and manual corrections.
