"""Write the slide deck on GloFAS v5 against v4 thresholds from the comparison table, so it only needs a rerun when the results change."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from analysis.glofas_v5_thresholds.compare_thresholds import (
    COMPARISON_FILENAME,
    RECENT_YEARS,
    RESULTS_DIRECTORY,
    V4_PUBLISHED_FIRST_YEAR,
    V4_PUBLISHED_LAST_YEAR,
    V5_FIRST_YEAR,
)
from analysis.glofas_v5_thresholds.download_reanalysis import LAST_YEAR
from analysis.glofas_v5_thresholds.propose_station_locations import PROPOSAL_FILENAME
from analysis.glofas_v5_thresholds.station_cells import (
    Placement,
    SQUARE_METRES_PER_SQUARE_KILOMETRE,
)
from analysis.glofas_v5_thresholds.stations import GLOFAS_CELL_SIZE_DEGREES
from data_management.seed_data_management.flood.build_glofas_return_period_curves import (
    DEFAULT_CACHE_DIRECTORY,
    LATITUDE,
    load_global_curves,
    LONGITUDE,
    UPSTREAM_AREA,
)
from matplotlib.colors import LogNorm
from matplotlib.patches import Patch, Rectangle
from pipelines.flood.constants import MINIMUM_RETURN_PERIOD_YEARS
from shared.data_helpers import target_countries_iso_a3

SLIDES_FILENAME = "glofas_v5_thresholds_slides.md"
RATIO_CHART_FILENAME = "threshold_ratio_by_station.png"
LOCATION_CHART_FILENAME = "station_locations.png"
ALERT_THRESHOLD = f"rp{MINIMUM_RETURN_PERIOD_YEARS:g}"
ALERT_THRESHOLD_NAME = f"{MINIMUM_RETURN_PERIOD_YEARS:g}-year threshold"
CHECK_RETURN_PERIODS = [1.5, 5.0, 20.0]
LARGE_DROP_RATIO = 0.5
LARGE_RISE_RATIO = 1.5
# The trend step matters for a station when it changes the v5 threshold by more than this share.
TREND_STEP_RELEVANCE = 0.1
TREND_STEP_EXAMPLES = 6
CHART_MAXIMUM_RATIO = 2.2
LOCATION_CHART_RADIUS_CELLS = 2
LOCATION_CHART_BOUNDARY_EXAMPLES = 2

MOVED_TO_RIVER = str(Placement.MOVED_TO_RIVER)
GROUP_COLOURS = {"same": "tab:blue", MOVED_TO_RIVER: "tab:orange"}


@dataclass(frozen=True)
class Groups:
    compared: pd.DataFrame
    large_drop: pd.DataFrame
    large_rise: pd.DataFrame
    trend_step_relevant: pd.DataFrame
    v5_river_moved: pd.DataFrame


@dataclass(frozen=True)
class Locations:
    proposal: pd.DataFrame
    on_boundary: pd.DataFrame
    next_to_smaller_stream: pd.DataFrame
    moved_to_river: pd.DataFrame


def main() -> None:
    table = add_ratios(pd.read_csv(RESULTS_DIRECTORY / COMPARISON_FILENAME))
    groups = group_stations(table)
    locations = group_locations(pd.read_csv(RESULTS_DIRECTORY / PROPOSAL_FILENAME))
    plot_threshold_ratios(groups.compared, RESULTS_DIRECTORY / RATIO_CHART_FILENAME)
    plot_station_locations(locations, RESULTS_DIRECTORY / LOCATION_CHART_FILENAME)
    slides = [
        title_slide(table, groups, locations),
        method_slide(),
        check_slide(table),
        differences_slide(groups),
        switch_together_slide(table, groups),
        v5_next_steps_slide(groups),
        locations_slide(locations),
        why_now_slide(locations, groups),
        location_proposal_slide(locations, groups),
        trend_step_backup_slide(groups),
    ]
    output_path = RESULTS_DIRECTORY / SLIDES_FILENAME
    output_path.write_text(
        _front_matter() + "\n\n" + "\n\n---\n\n".join(slides) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {output_path}")


def add_ratios(table: pd.DataFrame) -> pd.DataFrame:
    """Per station: v5 / v4 alert threshold, split into the model change and the trend step."""
    return table.assign(
        ratio=table[f"v5_{ALERT_THRESHOLD}"] / table[f"v4_{ALERT_THRESHOLD}"],
        model_ratio=table[f"v5_unadjusted_{ALERT_THRESHOLD}"]
        / table[f"v4_{ALERT_THRESHOLD}"],
        trend_step_ratio=table[f"v5_{ALERT_THRESHOLD}"]
        / table[f"v5_unadjusted_{ALERT_THRESHOLD}"],
    )


def group_stations(table: pd.DataFrame) -> Groups:
    return Groups(
        compared=table,
        large_drop=table[table["ratio"] < LARGE_DROP_RATIO].sort_values("ratio"),
        large_rise=table[table["ratio"] > LARGE_RISE_RATIO].sort_values(
            "ratio", ascending=False
        ),
        trend_step_relevant=table[
            (table["trend_step_ratio"] - 1).abs() > TREND_STEP_RELEVANCE
        ],
        v5_river_moved=table[table["v5_station_next_to_river"]],
    )


def group_locations(proposal: pd.DataFrame) -> Locations:
    on_boundary = proposal[proposal["placement"] == str(Placement.ON_CELL_BOUNDARY)]
    return Locations(
        proposal=proposal,
        on_boundary=on_boundary,
        next_to_smaller_stream=on_boundary[
            on_boundary["forecast_may_come_from_smaller_stream"]
        ],
        moved_to_river=proposal[proposal["placement"] == MOVED_TO_RIVER],
    )


def title_slide(table: pd.DataFrame, groups: Groups, locations: Locations) -> str:
    compared = groups.compared
    missing_countries = sorted(set(target_countries_iso_a3) - set(table["country"]))
    status = (
        f" Not yet in the v5 comparison: {', '.join(missing_countries)}, still downloading."
        if missing_countries
        else ""
    )
    location_fixes = len(locations.next_to_smaller_stream) + len(
        locations.moved_to_river
    )
    return f"""# GloFAS v5 thresholds for NRW, and a station fix found along the way

Preview for AB#45890, {date.today():%-d %B %Y}: our own v5 thresholds, computed with ECMWF's method.{status}

**Question:** what do the GloFAS v5 thresholds mean for NRW?

- **Answer:** they are lower, median {_ratio(compared["ratio"].median())} of v4, so forecasts and thresholds must switch to v5 together.
- Our method reproduces ECMWF's v4 thresholds exactly.

**Found along the way, independent of v5:** {location_fixes} station coordinates point at the wrong cell. A small fix, now (AB#45972)."""


def method_slide() -> str:
    return f"""<!-- _class: small -->

## The question, and how we can answer it before ECMWF publishes

**Question:** how do NRW's flood thresholds change with GloFAS v5?

**Missing:** ECMWF's v5 threshold files.

**Available:** the [v5 reanalysis](https://ewds.climate.copernicus.eu/datasets/cems-glofas-historical), {V5_FIRST_YEAR}–{LAST_YEAR}; the method ([thresholds](https://confluence.ecmwf.int/spaces/CEMS/pages/715612883/GloFAS+flood+threshold+generation), [trend step](https://confluence.ecmwf.int/spaces/CEMS/pages/715612910/Handling+of+non-stationarity+in+the+flood+thresholds)); ECMWF's [code](https://github.com/ec-jrc/lisflood-utilities), to which we added the trend step.

**Per station:**

1. Take the highest discharge of each year.
2. **New in v5:** where yearly peaks clearly rise or fall, shift older years towards the {LAST_YEAR} level.
3. Fit the same curve as for v4 (Gumbel) and read off the thresholds.

**Limits:** a preview, to be replaced by ECMWF's files; reanalysis only."""


def check_slide(table: pd.DataFrame) -> str:
    checked = table[table[f"v4_reproduced_{ALERT_THRESHOLD}"].notna()]
    rows = [
        [
            f"{row['country']} {row['station_code']}",
            *[
                f"{_threshold(row, 'v4', rp):,.0f} / {_threshold(row, 'v4_reproduced', rp):,.0f} / {_threshold(row, 'seed', rp):,.0f}"
                for rp in CHECK_RETURN_PERIODS
            ],
        ]
        for _, row in checked.iterrows()
    ]
    return f"""<!-- _class: small -->

## Check: on the v4 reanalysis, we get exactly ECMWF's v4 thresholds

The same calculation without the trend step, on v4 {V4_PUBLISHED_FIRST_YEAR}–{V4_PUBLISHED_LAST_YEAR}. Thresholds in m³/s: **ECMWF / ours / NRW seed data**

{_markdown_table(["Station", *[f"{rp:g} years" for rp in CHECK_RETURN_PERIODS]], rows)}

Checked for {len(checked)} stations only, to save download time."""


def switch_together_slide(table: pd.DataFrame, groups: Groups) -> str:
    compared = groups.compared
    station_years = RECENT_YEARS * len(compared)
    against_v5 = int(compared["v5_recent_trigger_years"].sum())
    against_v4 = int(compared["v5_against_v4_threshold_recent_trigger_years"].sum())
    with_v4_reanalysis = table[table["v4_recent_trigger_years"].notna()]
    v4_station_years = RECENT_YEARS * len(with_v4_reanalysis)
    v4_against_v4 = int(with_v4_reanalysis["v4_recent_trigger_years"].sum())
    v4_countries = ", ".join(sorted(with_v4_reanalysis["country"].unique()))
    rows = [
        [
            f"v4 against v4 thresholds ({v4_countries}, {len(with_v4_reanalysis)} stations)",
            f"{v4_against_v4 / v4_station_years:.0%}",
        ],
        ["v5 against v5 thresholds", f"{against_v5 / station_years:.0%}"],
        ["v5 against today's v4 thresholds", f"{against_v4 / station_years:.0%}"],
    ]
    return f"""## Answer: switch the forecasts and the thresholds to v5 at the same moment

v5 thresholds are generally lower than v4: median {_ratio(compared["ratio"].median())}, because v5 simulates lower river flows.

{_markdown_table([f"Share of years reaching the {ALERT_THRESHOLD_NAME}, {LAST_YEAR - RECENT_YEARS + 1}–{LAST_YEAR}", ""], rows)}

**So v5 forecasts need v5 thresholds:** with today's thresholds, far fewer alerts."""


def differences_slide(groups: Groups) -> str:
    compared = groups.compared
    rows = [
        [
            country,
            str(len(ratios)),
            _ratio(ratios.median()),
            f"{_ratio(ratios.min())} – {_ratio(ratios.max())}",
            str(int((ratios < 1).sum())),
        ]
        for country, ratios in compared.groupby("country")["ratio"]
    ]
    return f"""<!-- _class: chart -->

## Answer: v5 thresholds are lower than v4 at most stations

![w:1100]({RATIO_CHART_FILENAME})

{_markdown_table(["Country", "Stations", "Median v5 / v4", "Range", "Lower in v5"], rows)}"""


def locations_slide(locations: Locations) -> str:
    return f"""<!-- _class: dense -->

## Found along the way: some station coordinates point at the wrong cell

![w:1100]({LOCATION_CHART_FILENAME})

v4 upstream area per cell (km²), north up, 0.05° cells. **Red dot:** seed coordinates. **Orange:** proposed river cell.

- **On a cell boundary ({len(locations.next_to_smaller_stream)} stations):** the forecast may come from the touching cell that is a much smaller stream.
- **Off the river ({len(locations.moved_to_river)} stations):** forecast and thresholds come from a small cell next to the river."""


def location_proposal_slide(locations: Locations, groups: Groups) -> str:
    changed = pd.concat([locations.moved_to_river, locations.next_to_smaller_stream])
    v5_thresholds = groups.compared.set_index("station_code")[f"v5_{ALERT_THRESHOLD}"]
    rows = [
        [
            f"{row['country']} {row['station_code']}",
            f"{row['latitude']:.4f}, {row['longitude']:.4f}",
            f"{row['proposed_latitude']:.3f}, {row['proposed_longitude']:.3f}",
            (
                f"{row['smallest_touching_upstream_area_square_kilometres']:,.0f}"
                if row["placement"] == MOVED_TO_RIVER
                else f"{row['smallest_touching_upstream_area_square_kilometres']:,.0f} or {row['proposed_upstream_area_square_kilometres']:,.0f}"
            ),
            f"{row['proposed_upstream_area_square_kilometres']:,.0f}",
            (
                f"{row[f'seed_{ALERT_THRESHOLD}']:,.0f} → {row[f'proposed_v4_{ALERT_THRESHOLD}']:,.0f}"
                if row["thresholds_change"]
                else f"{row[f'seed_{ALERT_THRESHOLD}']:,.0f}, same"
            ),
            (
                f"{v5_thresholds[row['station_code']]:,.0f}"
                if row["station_code"] in v5_thresholds.index
                else "pending"
            ),
        ]
        for _, row in changed.iterrows()
    ]
    return f"""<!-- _class: tiny -->

## Proposal: move {len(changed)} stations to the centre of their river cell

{_markdown_table(["Station", "Coordinates now", "Proposed", "Forecast cell now, km²", "Proposed, km²", "v4 threshold: now → fixed", "v5 threshold, fixed"], rows)}

Upstream area of the cell the forecast comes from: on a boundary, either touching cell. {ALERT_THRESHOLD_NAME} in m³/s.

- **Off the river:** GloFAS's own river cell, checked in the GloFAS viewer. **On a boundary:** the river cell of today's thresholds.
- **How:** seed-data PR, and a database migration for test, staging and production (AB#45972)."""


def v5_next_steps_slide(groups: Groups) -> str:
    rows = [
        [
            "Switch forecasts and thresholds together",
            "All",
            "Migration process (AB#45893)",
        ],
        [
            f"Large drop, below {_ratio(LARGE_DROP_RATIO)}",
            _station_list(groups.large_drop),
            "Ask the GloFAS team (AB#45889)",
        ],
        [
            f"Large rise, above {_ratio(LARGE_RISE_RATIO)}",
            _station_list(groups.large_rise),
            "Same",
        ],
        [
            "Before going live",
            "All",
            "ECMWF's v5 files; update path for production, tested on test and staging",
        ],
    ]
    return f"""<!-- _class: dense -->

## Next steps for v5

{_markdown_table(["What", "Stations", "Action"], rows)}"""


def why_now_slide(locations: Locations, groups: Groups) -> str:
    return f"""## Independent of v5, but worth fixing now

**Independent of v4 or v5:** the coordinates are wrong today, and {_v5_river_summary(groups)[0].lower() + _v5_river_summary(groups)[1:]} So the fix holds after the switch.

**Why now, here:**

- **It affects alerts today:** {len(locations.next_to_smaller_stream)} stations may read their forecast from a much smaller stream; {len(locations.moved_to_river)} compare a small stream with its own thresholds.
- **It is small:** 17 entries in the seed data, one database migration.
- **The v5 thresholds are then computed at the right cells.**

**Why not more:** a stationless approach may replace stations (spike to come), so only these clear wins; no full review of all stations."""


def trend_step_backup_slide(groups: Groups) -> str:
    compared = groups.compared
    relevant = groups.trend_step_relevant
    largest = relevant.reindex(
        (relevant["trend_step_ratio"] - 1).abs().sort_values(ascending=False).index
    ).head(TREND_STEP_EXAMPLES)
    rows = [
        [
            f"{row['country']} {row['station_code']}",
            f"{_threshold(row, 'v4', MINIMUM_RETURN_PERIOD_YEARS):,.0f}",
            f"{_threshold(row, 'v5_unadjusted', MINIMUM_RETURN_PERIOD_YEARS):,.0f}",
            f"{_threshold(row, 'v5', MINIMUM_RETURN_PERIOD_YEARS):,.0f}",
            f"{100 * row['v5_trend_per_decade_relative']:+.0f}%",
        ]
        for _, row in largest.iterrows()
    ]
    table = (
        f"Where the trend step matters most, {ALERT_THRESHOLD_NAME} in m³/s:\n\n"
        + _markdown_table(
            ["Station", "v4", "v5 without trend step", "v5", "Trend per decade"], rows
        )
        if rows
        else ""
    )
    return f"""<!-- _class: dense -->

## Backup: the new model causes most of the change, not the trend step

- **Model:** v5 without trend step / v4, median {_ratio(compared["model_ratio"].median())}.
- **Trend step:** v5 / v5 without trend step, median {_ratio(compared["trend_step_ratio"].median())}; more than {TREND_STEP_RELEVANCE:.0%} change at {len(relevant)} of {len(compared)} stations. It is the one step we could not check against ECMWF.

{table}"""


def plot_threshold_ratios(compared: pd.DataFrame, output_path: Path) -> None:
    """Vertical bars per station, grouped by country, on a linear axis."""
    figure, axis = plt.subplots(figsize=(13, 3.8))
    position = 0
    tick_positions: list[int] = []
    tick_labels: list[str] = []
    for country, stations in compared.sort_values(["country", "ratio"]).groupby(
        "country"
    ):
        start = position
        for _, row in stations.iterrows():
            value = min(row["ratio"], CHART_MAXIMUM_RATIO)
            axis.bar(
                position,
                value,
                color=GROUP_COLOURS.get(row["placement"], GROUP_COLOURS["same"]),
                width=0.8,
            )
            if row["ratio"] > CHART_MAXIMUM_RATIO:
                axis.text(
                    position,
                    value,
                    f"{row['ratio']:.1f}",
                    ha="center",
                    va="bottom",
                    fontsize=6,
                )
            tick_positions.append(position)
            tick_labels.append(row["station_code"])
            position += 1
        axis.text(
            (start + position - 1) / 2,
            CHART_MAXIMUM_RATIO * 1.02,
            country,
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
        )
        axis.axvline(position, color="grey", linewidth=0.6)
        position += 1
    axis.axhline(1, color="black", linewidth=0.9)
    axis.set_xlim(-1, position - 1)
    axis.set_ylim(0, CHART_MAXIMUM_RATIO)
    axis.set_yticks(np.arange(0, CHART_MAXIMUM_RATIO, 0.5))
    axis.grid(axis="y", color="lightgrey", linewidth=0.5)
    axis.set_axisbelow(True)
    axis.set_xticks(tick_positions, tick_labels, rotation=90, fontsize=6)
    axis.set_ylabel(f"v5 / v4, {ALERT_THRESHOLD_NAME}")
    axis.legend(
        handles=[
            Patch(color=GROUP_COLOURS["same"], label="Station's own cell"),
            Patch(
                color=GROUP_COLOURS[MOVED_TO_RIVER],
                label="Moved to the river cell (proposed coordinates)",
            ),
        ],
        fontsize=7,
        loc="upper left",
    )
    for spine in ("top", "right"):
        axis.spines[spine].set_visible(False)
    figure.tight_layout()
    figure.savefig(output_path, dpi=150)
    plt.close(figure)


def plot_station_locations(locations: Locations, output_path: Path) -> None:
    """The v4 upstream area around the stations off the river and the clearest boundary cases."""
    boundary_examples = locations.next_to_smaller_stream.assign(
        share=locations.next_to_smaller_stream[
            "smallest_touching_upstream_area_square_kilometres"
        ]
        / locations.next_to_smaller_stream["proposed_upstream_area_square_kilometres"]
    ).nsmallest(LOCATION_CHART_BOUNDARY_EXAMPLES, "share")
    examples = pd.concat([boundary_examples, locations.moved_to_river])
    if examples.empty:
        return
    upstream_area = load_global_curves("v4", DEFAULT_CACHE_DIRECTORY)[UPSTREAM_AREA]
    figure, axes = plt.subplots(
        1, len(examples), figsize=(2.3 * len(examples), 2.6), squeeze=False
    )
    radius = LOCATION_CHART_RADIUS_CELLS
    half_cell = GLOFAS_CELL_SIZE_DEGREES / 2
    for axis, (_, station) in zip(axes.flat, examples.iterrows()):
        offsets = np.arange(-radius, radius + 1) * GLOFAS_CELL_SIZE_DEGREES
        latitudes = np.round(station["proposed_latitude"] - offsets, 3)
        longitudes = np.round(station["proposed_longitude"] + offsets, 3)
        areas = (
            upstream_area.sel(
                {LATITUDE: latitudes, LONGITUDE: longitudes}, method="nearest"
            ).to_numpy()
            / SQUARE_METRES_PER_SQUARE_KILOMETRE
        )
        axis.imshow(
            areas,
            cmap="Blues",
            norm=LogNorm(vmin=10, vmax=max(float(np.nanmax(areas)), 100)),
            extent=(
                longitudes[0] - half_cell,
                longitudes[-1] + half_cell,
                latitudes[-1] - half_cell,
                latitudes[0] + half_cell,
            ),
        )
        for row, latitude in enumerate(latitudes):
            for column, longitude in enumerate(longitudes):
                area = areas[row, column]
                axis.text(
                    longitude,
                    latitude,
                    _compact_area(area),
                    ha="center",
                    va="center",
                    fontsize=5,
                    color="white" if area > np.sqrt(np.nanmax(areas) * 10) else "black",
                )
        axis.add_patch(
            Rectangle(
                (
                    station["proposed_longitude"] - half_cell,
                    station["proposed_latitude"] - half_cell,
                ),
                GLOFAS_CELL_SIZE_DEGREES,
                GLOFAS_CELL_SIZE_DEGREES,
                fill=False,
                edgecolor=GROUP_COLOURS[MOVED_TO_RIVER],
                linewidth=2,
            )
        )
        axis.plot(
            station["longitude"], station["latitude"], "o", color="red", markersize=4
        )
        placement = (
            "off the river"
            if station["placement"] == MOVED_TO_RIVER
            else "on a boundary"
        )
        axis.set_title(
            f"{station['country']} {station['station_code']}, {placement}", fontsize=7
        )
        axis.set_xticks([])
        axis.set_yticks([])
    figure.tight_layout()
    figure.savefig(output_path, dpi=150)
    plt.close(figure)


def _compact_area(square_kilometres: float) -> str:
    if not np.isfinite(square_kilometres):
        return ""
    if square_kilometres >= 10_000:
        return f"{square_kilometres / 1000:.0f}k"
    if square_kilometres >= 1_000:
        return f"{square_kilometres / 1000:.1f}k"
    return f"{square_kilometres:.0f}"


def _v5_river_summary(groups: Groups) -> str:
    moved = groups.v5_river_moved
    if moved.empty:
        return f"In v5 the river is in the same cell as in v4, at all {len(groups.compared)} compared stations."
    return f"In v5 the river moved to the next cell at {len(moved)} of {len(groups.compared)} compared stations: {_station_list(moved)}."


def _threshold(row: pd.Series, prefix: str, return_period: float) -> float:
    return float(row[f"{prefix}_rp{return_period:g}"])


def _front_matter() -> str:
    return """---
marp: true
paginate: true
size: 16:9
style: |
  section { font-size: 24px; padding: 56px 56px 44px; }
  h1 { font-size: 40px; }
  h2 { font-size: 32px; }
  section.chart img { display: block; margin: 0 auto; }
  section.chart table { font-size: 15px; margin: 8px auto 0; }
  section.chart td, section.chart th { padding: 2px 12px; }
  section.small { font-size: 21px; }
  section.small table { font-size: 18px; }
  section.small td, section.small th { padding: 4px 14px; }
  section.dense { font-size: 19px; }
  section.dense h2 { font-size: 28px; }
  section.dense table { font-size: 16px; }
  section.dense td, section.dense th { padding: 3px 10px; }
  section.tiny { font-size: 17px; }
  section.tiny h2 { font-size: 26px; }
  section.tiny table { font-size: 13px; }
  section.tiny td, section.tiny th { padding: 1px 8px; }
---"""


def _markdown_table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def _station_list(stations: pd.DataFrame) -> str:
    return ", ".join(stations["station_code"]) if not stations.empty else "None"


def _ratio(value: float) -> str:
    return f"×{value:.2f}"


if __name__ == "__main__":
    main()
