# Flood footprint from a return period per GloFAS cell

Analysis for the first slice of spike AB#42674: the flood footprint of an alert comes from a return period per GloFAS cell, with depth interpolated between the flood maps. The method itself is in `pipelines/flood/` (see its README).

Both scripts read their inputs from a local clone of the seed repo (`SEED_DATA_REPO_ROOT` in `data/.env`) and from `data/data/`. They do not need the NRW API.

## Inputs

```bash
cd data
# GloFAS return period curves per country, into data/data/ while they are not in the seed repo
uv run python -m data_management.seed_data_management.flood.build_glofas_return_period_curves \
  --output-directory data/glofas-return-period-curves
```

`compare_footprints.py` also needs an archived forecast with all ensemble members. The default is the Malawi forecast of 2 September 2026 in `data/data/glofas/country_split_alert/20260902/`.

## Scripts

- `compare_footprints.py` compares today's footprint with the new one for the stations that trigger: flooded area and exposed population per regridding method and minimum depth, and a figure per minimum depth. It also computes the new footprint without one of its rules at a time (small streams driving too, no dry floor), and draws per station the steps from today's footprint to the new one, and what the small streams rule and the regridding method do. It also compares the station's return period with the one of its cell, and runs the flood `forecast.py` on the same inputs.
- `check_curve_source.py` checks at every station whether its thresholds lie on the GloFAS curve of its cell.
- `check_sensitivity.py` shows how much the results depend on the three values that are not agreed: exposed population per minimum flood depth and per minimum upstream area on the archived forecast, the share of cells with flooding in the flood maps per class of upstream area (with a chart), how far the flooding in the flood maps lies from a driving cell per minimum upstream area, and what a minimum curve scale switches off, in each country and inside the areas of its alerts, next to the cells above 100 years in one forecast and the discharge they carry. The minimum curve scale in the pipeline is provisional and rests on this. That last part needs one ensemble member of a global forecast; the default is `data/data/glofas/raw/20261029/dis_00_2026102900.nc`. It also counts the stations whose footprint can be empty at a low alert level. What the app shows for such a station is checked by hand: run it through `pipelines/test/manual_checks/flood_station_sweep.py` with `--output-mode api` against a local API.
- `plot_open_decisions.py` gives the counts and charts behind the open decisions on which cells drive the footprint: the share of large-river cells and of near-flat curves per country (`driving_cells.csv`), where the flooding in the flood maps lies relative to the large-river cells (`flood_map_wet_pixels.csv`), an ordinary curve and a near-flat one on the same axis, and the cells around the stations whose own cell does not drive the footprint. The two charts are not in the slide deck.

```bash
uv run python -m analysis.flood_footprint.compare_footprints
uv run python -m analysis.flood_footprint.check_curve_source
uv run python -m analysis.flood_footprint.check_sensitivity
uv run python -m analysis.flood_footprint.plot_open_decisions
```

Results are written to `results/`. `results/flood_footprint_slides.md` is a short [Marp](https://marp.app) slide deck on the method and the results; its texts and tables are written by hand, so check them after the numbers change.
