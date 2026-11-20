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

- `compare_footprints.py` compares today's footprint with the new one for the stations that trigger: flooded area and exposed population per regridding method and minimum depth, a figure per minimum depth, and a summary figure per station. It also compares the station's return period with the one of its cell, and runs the flood `forecast.py` on the same inputs.
- `check_curve_source.py` checks at every station whether its thresholds lie on the GloFAS curve of its cell.
- `plot_open_decisions.py` draws the charts behind two open decisions: an ordinary curve next to a near-flat one, with the share of near-flat cells per country, and the cells around the stations whose own cell does not drive the footprint.

```bash
uv run python -m analysis.flood_footprint.compare_footprints
uv run python -m analysis.flood_footprint.check_curve_source
uv run python -m analysis.flood_footprint.plot_open_decisions
```

Results are written to `results/`. `results/flood_footprint_slides.md` is a short [Marp](https://marp.app) slide deck on the method and the results; its texts and tables are written by hand, so check them after the numbers change.
