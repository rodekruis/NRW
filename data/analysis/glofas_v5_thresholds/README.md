# GloFAS v5 flood thresholds against v4

Analysis for AB#45890 (part of AB#45592): how the GloFAS v5 flood thresholds of the NRW stations differ from today's v4 thresholds, before ECMWF publishes the official v5 threshold files.

ECMWF's v5 method ([threshold generation](https://confluence.ecmwf.int/spaces/CEMS/pages/715612883/GloFAS+flood+threshold+generation), [trend adjustment](https://confluence.ecmwf.int/spaces/CEMS/pages/715612910/Handling+of+non-stationarity+in+the+flood+thresholds)):

1. Take the annual maxima of the daily discharge reanalysis, 1980–2025.
2. Shift each year's maximum to the 2025 level of its linear trend, weighted by √R² of that trend: `Qadj(t) = max[0, Q(t) + √R² × slope × (2025 − t)]`.
3. Fit a Gumbel distribution with L-moments, as for v4.

## Station locations

A station's forecast and thresholds come from the GloFAS cell of its coordinates (the pipeline samples the forecast there). `station_cells.py` places each station on one cell, the same for v4 and v5:

- **Inside one cell:** that cell.
- **On a cell boundary:** the pipeline's rounding decides between the touching cells. Of these, the cell whose v4 curve gives the seed thresholds, else the largest river.
- **On a cell that drains less than 250 km²,** the smallest v4 reporting point: GloFAS's own river cell for the station, else the largest river among the cells right around it.

`propose_station_locations.py` writes these as new coordinates for the seed data, in `results/station_location_proposal.csv`. It needs only ECMWF's v4 files, so it covers all stations. For the stations off the river, `glofas_viewer_river_cells.csv` holds GloFAS's own river cell, looked up by hand in the GloFAS viewer (LISFLOOD X/Y in a reporting point's pop-up). The fixes with an effect on the alerts were applied to the seed data once, with a production data migration (AB#45972).

## Scripts

All scripts read the stations from a local clone of the seed repo (`SEED_DATA_REPO_ROOT` in `data/.env`). They do not need the NRW API.

- `download_reanalysis.py` downloads the v4 (1979–2025) and v5 (1980–2025) daily discharge from the [CEMS Early Warning Data Store](https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical). The stations are grouped into boxes; the data store allows one year per request. Downloads go to `data/data/glofas-reanalysis/` and are skipped when already there, so an interrupted run can be resumed. It then keeps a 7×7-cell window around each station's cell in `station_discharge_<version>.nc`.
- `compare_thresholds.py` computes the v5 thresholds per station, with and without the trend step, and compares them with the v4 thresholds of the same cell. It checks the method by refitting v4 (1979–2022) against ECMWF's published v4 curves, and checks whether the river moved to a neighbouring cell in v5.
- `make_slides.py` writes `results/glofas_v5_thresholds_slides.md`, a short [Marp](https://marp.app) slide deck, and its charts from the comparison and the location proposal. Its texts are filled in from the results, so rerun it after these change instead of editing the deck.

```bash
cd data
# Pilot: the Malawi stations, in a small box
uv run python -m analysis.glofas_v5_thresholds.download_reanalysis --countries MWI --maximum-span-degrees 3
# All stations
uv run python -m analysis.glofas_v5_thresholds.download_reanalysis
uv run python -m analysis.glofas_v5_thresholds.propose_station_locations
uv run python -m analysis.glofas_v5_thresholds.compare_thresholds
uv run python -m analysis.glofas_v5_thresholds.make_slides
```

The data store runs one request at a time, a few minutes each, and allows one year per request, so a version takes about 46 requests per box. The area barely matters, so by default all stations are downloaded in a few large boxes. Only the Malawi stations have the v4 reanalysis, for the check; the other stations are compared with ECMWF's published v4 curves.

The data store uses the same ECMWF API key as the Climate Data Store: `CDSAPI_KEY` in `data/.env`. Accept the dataset licence once on its [download page](https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical?tab=download#manage-licences).

Results are written to `results/`: `station_threshold_comparison.csv` with a row per station, `station_location_proposal.csv`, the slide deck and its charts.

## Limits

- These are previews of the v5 thresholds, to be replaced by ECMWF's files once published.
- They use the station cells above. Where ECMWF's v5 reporting points place a station elsewhere, ECMWF's v5 threshold will differ.
- This compares the reanalysis only, not the forecasts.
