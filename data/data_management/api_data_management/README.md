# Updating data in a deployed API

Seed/reset is not available in production. When a change to seeded data has to reach an existing database, a script here writes it into a deployed API through its admin endpoints.

Each script:

- reads the data from the same source as the seed (the seed-data repo, or the api-service seed in code);
- reports what would change, and writes nothing by default;
- writes only with `--apply`, after it has asked for the admin password and a typed confirmation of the target host.

Try a script on a local API or on test/staging before production.

## Alert-config spatial extents

`update_alert_config_spatial_extents_in_api.py` sets `spatialExtentGeometry` on the existing alert configs, through `PATCH /api/alert-configs/{id}`:

- **floods:** per station, from `hazard/flood/glofas-stations/{ISO3}_station_spatial_extents.geojson` in the seed-data repo;
- **drought and compound floods:** per region, from `services/api-service/src/seed/seed-data/seed-alert-config-spatial-extents.json`.

A station with an area but no alert config gets one, through `POST /api/alert-configs`, with the lead times, class levels and trigger settings of the other flood alert configs of its country, as the seed does. If those differ within the country, the station is reported and not created.

Run it right after deploying a release with the migration that adds `spatialExtentGeometry`. Rerun it whenever the spatial extents change. The report lists the alert configs that have no geometry in these files: tropical cyclone and national drought (they cover the whole country), and stations without an area (the flood pipeline skips them).

```bash
cd data
uv run python -m data_management.api_data_management.update_alert_config_spatial_extents_in_api \
  --api-url https://<api-host> --admin-username <admin-email>
# check the report, then add --apply
```

The seed-data repo is `SEED_DATA_REPO_ROOT` in `data/.env`, or `--seed-repository`. Check it out at the revision the deployed API seeds from.
