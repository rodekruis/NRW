"""Propose new coordinates for the stations whose coordinates lie on a cell boundary or off the river, for the seed data."""

from __future__ import annotations

import pandas as pd
from analysis.glofas_v5_thresholds.compare_thresholds import (
    RESULTS_DIRECTORY,
    RETURN_PERIODS,
)
from analysis.glofas_v5_thresholds.gumbel import gumbel_threshold
from analysis.glofas_v5_thresholds.station_cells import locate_station_cell, Placement
from analysis.glofas_v5_thresholds.stations import load_stations
from data_management.seed_data_management.flood.build_glofas_return_period_curves import (
    DEFAULT_CACHE_DIRECTORY,
    LATITUDE,
    load_global_curves,
    LOCATION,
    LONGITUDE,
    SCALE,
)
from shared.data_helpers import get_seed_data_repo_path

PROPOSAL_FILENAME = "station_location_proposal.csv"
# A touching cell with less than this share of the proposed cell's upstream area is another, smaller stream.
SMALLER_STREAM_SHARE = 0.5


def main() -> None:
    v4_curves = load_global_curves("v4", DEFAULT_CACHE_DIRECTORY)
    rows = []
    for station in load_stations(get_seed_data_repo_path()):
        cell = locate_station_cell(station, v4_curves)
        if cell.placement == Placement.INSIDE_CELL:
            continue
        curve = v4_curves.sel(
            {LATITUDE: cell.latitude, LONGITUDE: cell.longitude}, method="nearest"
        )
        rows.append(
            {
                "country": station.country,
                "station_code": station.code,
                "station_name": station.name,
                "placement": str(cell.placement),
                "latitude": station.latitude,
                "longitude": station.longitude,
                "proposed_latitude": cell.latitude,
                "proposed_longitude": cell.longitude,
                "touching_cells": cell.touching_cells,
                "smallest_touching_upstream_area_square_kilometres": round(
                    cell.smallest_touching_upstream_area_square_kilometres
                ),
                "proposed_upstream_area_square_kilometres": round(
                    cell.upstream_area_square_kilometres
                ),
                # On a boundary, the pipeline's rounding decides between the touching cells; here one is a much smaller stream.
                "forecast_may_come_from_smaller_stream": cell.placement
                == Placement.ON_CELL_BOUNDARY
                and cell.smallest_touching_upstream_area_square_kilometres
                < SMALLER_STREAM_SHARE * cell.upstream_area_square_kilometres,
                "thresholds_change": not cell.seed_thresholds_on_cell,
                **{
                    f"seed_rp{return_period:g}": station.thresholds[return_period]
                    for return_period in RETURN_PERIODS
                },
                **{
                    f"proposed_v4_rp{return_period:g}": gumbel_threshold(
                        return_period, float(curve[LOCATION]), float(curve[SCALE])
                    )
                    for return_period in RETURN_PERIODS
                },
            }
        )
    proposal = pd.DataFrame(rows)
    RESULTS_DIRECTORY.mkdir(exist_ok=True)
    proposal.to_csv(RESULTS_DIRECTORY / PROPOSAL_FILENAME, index=False)
    print(
        proposal[
            [
                "country",
                "station_code",
                "placement",
                "latitude",
                "longitude",
                "proposed_latitude",
                "proposed_longitude",
                "smallest_touching_upstream_area_square_kilometres",
                "proposed_upstream_area_square_kilometres",
                "forecast_may_come_from_smaller_stream",
                "thresholds_change",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
