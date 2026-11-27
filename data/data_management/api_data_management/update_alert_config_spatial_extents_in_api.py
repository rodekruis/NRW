"""Fill in the spatial extent geometry of the alert configs in a deployed API.

Seed/reset is not available in production, so existing alert configs get their geometry here,
through PATCH /api/alert-configs/{id}:
- floods: from {ISO3}_station_spatial_extents.geojson in the seed-data repo, per station code;
- drought and compound floods: from seed-alert-config-spatial-extents.json in the api-service seed.

A station with an area but no alert config gets one, through POST /api/alert-configs, with the
settings of the other flood alert configs of its country, as the seed does.

Run it right after deploying the migration that adds the geometry column. Reports first: which
alert configs get a geometry, which already have it, which are created, and which have none in
these files (tropical cyclone and national drought, which cover the whole country, and a station
without an area, which the flood pipeline skips). Writes only with --apply, which asks for a typed
confirmation of the target host.

Usage, from the data directory (add --apply to write):
    uv run python -m data_management.api_data_management.update_alert_config_spatial_extents_in_api \\
        --api-url https://<api-host> --admin-username <admin-email>
"""

import argparse
import getpass
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from data_management.seed_data_management.flood.migrate_glofas_station_area_mapping import (
    STATION_THRESHOLDS_DIRECTORY,
)
from shared.data_helpers import get_seed_data_repo_path

ALERT_CONFIGS_PATH = "/api/alert-configs"
LOGIN_PATH = "/api/users/login"
REQUEST_TIMEOUT_SECONDS = 300
FLOODS_HAZARD_TYPE = "floods"
CODE_SPATIAL_EXTENTS_FILE = (
    Path(__file__).resolve().parents[3]
    / "services/api-service/src/seed/seed-data/seed-alert-config-spatial-extents.json"
)

# Copied from the other flood alert configs of the country when a station gets an alert config
FLOOD_SETTING_FIELDS = (
    "temporalExtents",
    "severityClassLevels",
    "probabilityClassLevels",
    "triggerAlertClass",
    "triggerLeadTimeDuration",
)

# (hazard type, country, spatial extent name)
AlertConfigKey = tuple[str, str, str]


@dataclass(frozen=True)
class AlertConfigUpdate:
    alert_config_id: int
    key: AlertConfigKey
    geometry: dict


def main() -> None:
    arguments = parse_arguments()
    seed_repository: Path = arguments.seed_repository or Path(get_seed_data_repo_path())
    api_url = arguments.api_url.rstrip("/")
    session = create_admin_session(api_url, arguments.admin_username)
    print(f"Target API: {api_url}")

    geometries = {
        **load_flood_geometries(seed_repository),
        **load_code_geometries(CODE_SPATIAL_EXTENTS_FILE),
    }
    alert_configs = fetch_alert_configs(session, api_url)
    updates, unchanged_count, without_geometry = plan_updates(alert_configs, geometries)
    creations, not_created = plan_creations(alert_configs, geometries)

    print(
        f"Alert configs: {len(alert_configs)}, to update {len(updates)}, "
        f"unchanged {unchanged_count}, without a geometry in the files {len(without_geometry)}, "
        f"to create {len(creations)}"
    )
    for key in without_geometry:
        print(f"  no geometry in the files: {format_key(key)}")
    for creation in creations:
        print(f"  to create: {format_key(get_key(creation))}")
    for key, reason in not_created:
        print(
            f"  geometry without an alert config, not created: {format_key(key)}: {reason}"
        )

    if not arguments.apply or not (updates or creations):
        return
    confirm_target(api_url)
    failed_count = sum(
        not patch_alert_config(session, api_url, update) for update in updates
    )
    print(f"Updated {len(updates) - failed_count}, failed {failed_count}")
    if creations:
        if create_alert_configs(session, api_url, creations):
            print(f"Created {len(creations)}")
        else:
            failed_count += len(creations)
    sys.exit(1 if failed_count else 0)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--admin-username", required=True)
    parser.add_argument(
        "--seed-repository",
        type=Path,
        default=None,
        help="Local clone of the seed repo. Default: SEED_DATA_REPO_ROOT in data/.env.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the reported updates after interactive confirmation",
    )
    return parser.parse_args()


def create_admin_session(api_url: str, admin_username: str) -> requests.Session:
    session = requests.Session()
    response = session.post(
        f"{api_url}{LOGIN_PATH}",
        json={
            "username": admin_username,
            "password": getpass.getpass(f"Password for {admin_username}: "),
        },
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    if not response.json().get("isAdmin"):
        raise RuntimeError(f"{admin_username} is not an admin")
    return session


def load_flood_geometries(seed_repository: Path) -> dict[AlertConfigKey, dict]:
    geometries: dict[AlertConfigKey, dict] = {}
    for path in sorted(
        (seed_repository / STATION_THRESHOLDS_DIRECTORY).glob(
            "*_station_spatial_extents.geojson"
        )
    ):
        country = path.name.split("_")[0]
        for feature in json.loads(path.read_text(encoding="utf-8"))["features"]:
            station_code = feature["properties"]["station_code"]
            geometries[(FLOODS_HAZARD_TYPE, country, station_code)] = feature[
                "geometry"
            ]
    return geometries


def load_code_geometries(path: Path) -> dict[AlertConfigKey, dict]:
    return {
        (
            feature["properties"]["hazardType"],
            feature["properties"]["countryCodeIso3"],
            feature["properties"]["spatialExtentName"],
        ): feature["geometry"]
        for feature in json.loads(path.read_text(encoding="utf-8"))["features"]
    }


def fetch_alert_configs(session: requests.Session, api_url: str) -> list[dict]:
    response = session.get(
        f"{api_url}{ALERT_CONFIGS_PATH}", timeout=REQUEST_TIMEOUT_SECONDS
    )
    response.raise_for_status()
    return response.json()


def get_key(alert_config: dict) -> AlertConfigKey:
    return (
        alert_config["hazardType"],
        alert_config["countryCodeIso3"],
        alert_config["spatialExtentName"],
    )


def format_key(key: AlertConfigKey) -> str:
    hazard_type, country, name = key
    return f"{hazard_type} {country} {name}"


def plan_updates(
    alert_configs: list[dict], geometries: dict[AlertConfigKey, dict]
) -> tuple[list[AlertConfigUpdate], int, list[AlertConfigKey]]:
    """The alert configs whose geometry changes, the number that already have it, and the
    alert configs that have no geometry in the files."""
    updates: list[AlertConfigUpdate] = []
    unchanged_count = 0
    without_geometry: list[AlertConfigKey] = []
    for alert_config in alert_configs:
        key = get_key(alert_config)
        geometry = geometries.get(key)
        if geometry is None:
            without_geometry.append(key)
        elif alert_config.get("spatialExtentGeometry") == geometry:
            unchanged_count += 1
        else:
            updates.append(
                AlertConfigUpdate(
                    alert_config_id=alert_config["id"],
                    key=key,
                    geometry=geometry,
                )
            )
    return updates, unchanged_count, sorted(without_geometry)


def plan_creations(
    alert_configs: list[dict], geometries: dict[AlertConfigKey, dict]
) -> tuple[list[dict], list[tuple[AlertConfigKey, str]]]:
    """New flood alert configs for the stations with a geometry but no alert config, with the
    settings of the other flood alert configs of the country, and the ones that can't be made.
    """
    configured_keys = {get_key(alert_config) for alert_config in alert_configs}
    creations: list[dict] = []
    not_created: list[tuple[AlertConfigKey, str]] = []
    for key in sorted(set(geometries) - configured_keys):
        hazard_type, country, name = key
        if hazard_type != FLOODS_HAZARD_TYPE:
            not_created.append((key, "only flood alert configs are created"))
            continue
        country_settings = {
            json.dumps(
                {field: alert_config[field] for field in FLOOD_SETTING_FIELDS},
                sort_keys=True,
            )
            for alert_config in alert_configs
            if get_key(alert_config)[:2] == (FLOODS_HAZARD_TYPE, country)
        }
        if len(country_settings) != 1:
            reason = (
                f"the flood alert configs of {country} differ in their settings"
                if country_settings
                else f"{country} has no flood alert configs to copy the settings from"
            )
            not_created.append((key, reason))
            continue
        creations.append(
            {
                "countryCodeIso3": country,
                "hazardType": hazard_type,
                "spatialExtentName": name,
                "spatialExtentGeometry": geometries[key],
                **json.loads(country_settings.pop()),
            }
        )
    return creations, not_created


def confirm_target(api_url: str) -> None:
    host = urlparse(api_url).netloc
    if input(f"Type '{host}' to write these updates: ").strip() != host:
        raise SystemExit("Not confirmed, nothing written")


def patch_alert_config(
    session: requests.Session, api_url: str, update: AlertConfigUpdate
) -> bool:
    response = session.patch(
        f"{api_url}{ALERT_CONFIGS_PATH}/{update.alert_config_id}",
        json={"spatialExtentGeometry": update.geometry},
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if response.ok:
        return True
    print(f"  {format_key(update.key)}: {response.status_code} {response.text[:200]}")
    return False


def create_alert_configs(
    session: requests.Session, api_url: str, creations: list[dict]
) -> bool:
    response = session.post(
        f"{api_url}{ALERT_CONFIGS_PATH}",
        json=creations,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    if response.ok:
        return True
    print(f"  create: {response.status_code} {response.text[:200]}")
    return False


if __name__ == "__main__":
    main()
