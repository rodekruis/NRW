# GloFAS v5 flood thresholds against v4

Analysis for AB#45890 (part of AB#45592): how the GloFAS v5 flood thresholds of the NRW stations differ from today's v4 thresholds, before ECMWF publishes the official v5 threshold files.

ECMWF's v5 method ([threshold generation](https://confluence.ecmwf.int/spaces/CEMS/pages/715612883/GloFAS+flood+threshold+generation), [trend adjustment](https://confluence.ecmwf.int/spaces/CEMS/pages/715612910/Handling+of+non-stationarity+in+the+flood+thresholds)):

1. Take the annual maxima of the daily discharge reanalysis, 1980–2025.
2. Shift each year's maximum to the 2025 level of its linear trend, weighted by √R² of that trend: `Qadj(t) = max[0, Q(t) + √R² × slope × (2025 − t)]`.
3. Fit a Gumbel distribution with L-moments, as for v4.

## Scripts

Both scripts read the stations from a local clone of the seed repo (`SEED_DATA_REPO_ROOT` in `data/.env`). They do not need the NRW API.

- `download_reanalysis.py` downloads the v4 (1979–2025) and v5 (1980–2025) daily discharge from the [CEMS Early Warning Data Store](https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical). The stations are grouped into boxes; the data store allows one year per request. Downloads go to `data/data/glofas-reanalysis/` and are skipped when already there, so an interrupted run can be resumed. It then keeps a 7×7-cell window around each station in `station_discharge_<version>.nc`.
- `compare_thresholds.py` computes the v5 thresholds per station, with and without the trend step, and compares them with the v4 thresholds. It checks the method by refitting v4 (1979–2022) against ECMWF's published v4 curves, and flags stations whose v5 cell has a very different typical discharge than v4, while a neighbouring cell matches: those are probably on another river cell in v5.

```bash
cd data
# Pilot: one box (Malawi)
uv run python -m analysis.glofas_v5_thresholds.download_reanalysis --boxes box_10
# All stations, about 1,900 requests of a few minutes each
uv run python -m analysis.glofas_v5_thresholds.download_reanalysis
uv run python -m analysis.glofas_v5_thresholds.compare_thresholds
```

The data store uses the same ECMWF API key as the Climate Data Store: `CDSAPI_KEY` in `data/.env`. Accept the dataset licence once on its [download page](https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical?tab=download#manage-licences).

Results are written to `results/`: `station_threshold_comparison.csv` with a row per station, and `threshold_ratio_by_station.png` with the v5 / v4 ratio of the trigger (1.5-year) threshold.

## Limits

- These are previews of the v5 thresholds, to be replaced by ECMWF's files once published.
- They use the station's v4 coordinates. Where v5 moves a station to another cell, ECMWF's v5 threshold will differ.
- This compares the reanalysis only, not the forecasts.
