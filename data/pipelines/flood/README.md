# Flood Pipeline Logic (WIP)

This folder contains the flood-specific forecast logic used by the pipeline framework.

## Main script

- `flood/forecast.py`
  - Entry point for flood hazard logic via `calculate_flood_forecasts(...)`:
  - Loads station points and admin areas through `DataProvider`, then combines them with GloFAS discharge data (from FTP or seed-repo mock files).
  - Builds alerts, severity time series, admin-area exposure, and raster exposure through `DataSubmitter`.

## Accompanying scripts in this folder

- `extract_forecast.py`
  - Samples GloFAS discharge values from (sliced) NetCDF rasters at station coordinates.
  - Produces per-station, per-lead-time ensemble discharge series.
  - Reads the ensemble-median discharge per GloFAS cell, on the day the station peaks, for the flood footprint.

- `compute_flood_depth.py`
  - Computes the flood footprint of an alert, see [Flood footprint](#flood-footprint).

- `footprint_method.py`
  - The method behind the footprint, on plain arrays and grids: discharge to return period, return period onto the flood map grid, return period to depth.

- `determine_exposure.py`
  - Filters the station-to-admin-area mapping to place codes present in the loaded admin areas, and builds the boundary around them.

- `pipelines/infra/utils/raster.py`
  - Utility functions for geospatial preprocessing:
    - derive country bounding box from admin geometries,
    - slice NetCDF to country bounds,
    - clip rasters to bounding boxes,
    - get raster extent for output metadata.

## Flood footprint

The station decides whether there is an alert. The footprint of that alert comes from the GloFAS cells in its area, following the method of [CLIMADA's GloFAS river flood module](https://github.com/CLIMADA-project/climada_petals/blob/main/climada_petals/hazard/rf_glofas/transform_ops.py) in our own implementation:

1. **Return period per cell.** Each cell has its own Gumbel curve of annual peak discharge. Its ensemble-median discharge on the day the station's median discharge peaks gives a return period: `1 / (1 - exp(-exp(-(q - mu) / sigma)))`.
2. **Onto the flood map grid.** Each flood map pixel takes the return period of the nearest cell (`REGRIDDING_METHOD`). Small streams (`MINIMUM_UPSTREAM_AREA_SQUARE_KILOMETRES`) do not drive the footprint, and neither do cells whose curve is so flat that no water reads as a flood (`MINIMUM_GUMBEL_SCALE_CUBIC_METRES_PER_SECOND`); their pixels take the nearest cell that does.
3. **Depth.** Depth is interpolated linearly in return period between the flood maps, from zero depth at 1 year. Pixels below `MINIMUM_RETURN_PERIOD` stay dry, and depths below `MINIMUM_FLOOD_DEPTH_METRES` are left out.

The footprint is computed inside the boundary of the alert's admin areas. If the flood map for the station's return period shows no flooding there, the flood maps do not cover the area and there is no alert.

A triggered station keeps its alert when its footprint is empty: the alert then reports its whole area with nobody exposed. Without a gridded forecast on the grid of the curves, as with the mock forecasts, the whole area takes the station's return period.

The curves (`mu`, `sigma` and upstream area per cell, for `GLOFAS_VERSION`) are per-country files in the seed repo, built with `data_management/seed_data_management/flood/build_glofas_return_period_curves.py`.

## GloFAS discharge data

GloFAS discharge NetCDF files are sourced either from:

- **FTP** (`glofas_discharge_ftp`): Real-time ensemble forecast files from the GloFAS FTP server.
- **Seed-repo alert** (`glofas_discharge_seed_repo_alert`): Country-clipped mock file with values above thresholds (triggers alerts).
- **Seed-repo no-alert** (`glofas_discharge_seed_repo_no_alert`): Country-clipped mock file with values below thresholds (no alerts).

## `forecast.py` flow (read -> output)

1. Load core inputs:
   - Load GloFAS station metadata and target admin areas through `DataProvider`.
   - Load threshold JSON, population raster, flood depth rasters and GloFAS return period curves through `DataProvider`.
   - Stop early and record an error if stations or admin areas are missing.

2. Build country spatial extent
   - Compute country bounding box from target admin areas.
   - Slice NetCDF files once to this bounding box.

3. Process discharge per station
   - Iterate through stations and currently limit processing to the first two station entries.
   - Extract discharge ensemble values per lead time.
   - Derive lead-time severities from thresholds.
   - Skip stations with no threshold exceedance.

4. Build alert payload
   - Build the boundary of the station's admin areas.
   - Compute the flood depth inside that boundary from the return period per GloFAS cell.
   - Compute the exposed-population raster and aggregate exposed population per place code.

5. Compute exposure
   - Create one alert event per alerting station.
   - Add severity time-series data for ensemble runs and the median discharge.
   - Add admin-area population exposure per place code.
   - Add raster exposure metadata for the generated `flood_extent_{station_code}.tif`.

6. Write final output to local forecast folder
   - `forecast.py` fills `DataSubmitter`.
   - `pipelines/infra/run_forecasts.py` finalizes and writes `forecast.json`.
   - Default local base path is `pipelines/output`, resulting in paths like:
     - `pipelines/output/floods/{ISO3}/{timestamp}/forecast.json`
   - In this repository this appears under `data/pipelines/output/floods/...`.
