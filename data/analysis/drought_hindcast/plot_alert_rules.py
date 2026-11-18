"""Draw one forecast under the region rule and under the area rule, to show how they differ."""

import calendar
import math

import numpy as np
import pandas as pd
from analysis.drought_hindcast.calculate_alerts import (
    calculate_cell_shares_of_dry_members,
    load_rainfall,
    RegionRainfall,
)
from analysis.drought_hindcast.definitions import (
    AREA_RULE_ALERT_COLUMN,
    AREA_RULE_MINIMUM_AREA_SHARE,
    AREA_RULE_MINIMUM_PROBABILITY,
    DEFAULT_PROBABILITY_THRESHOLD,
    ForecastVariant,
    get_probability_alert_column,
    POOLED_REGION_SEASONS,
    REGION_SEASONS,
    RegionSeason,
)
from analysis.drought_hindcast.plot_skill import NEUTRAL_COLOUR, save_figure
from analysis.drought_hindcast.prepare_forecast_rainfall import SEAS5_CELL_SIZE_DEGREES
from analysis.drought_hindcast.study_area import (
    FORECAST_ALERTS_FILE,
    load_region_geometries,
)
from matplotlib.axes import Axes
from matplotlib.figure import Figure
from matplotlib.patches import Patch, PathPatch, Rectangle
from matplotlib.path import Path
from shapely.geometry import box, shape
from shapely.geometry.base import BaseGeometry

# A forecast on which the two rules disagree.
EXAMPLE_REGION_SEASON_NAME = "KEN National OND"
EXAMPLE_SEASON_YEAR = 1985
EXAMPLE_MONTHS_BEFORE_SEASON = 1

DRY_COLOUR = "#7c4a1e"
NOT_DRY_COLOUR = "#e5e7eb"
TEXT_ON_DRY_COLOUR = "white"
TEXT_ON_NOT_DRY_COLOUR = "#374151"
OUTLINE_COLOUR = "#111827"
MAP_MARGIN_DEGREES = 0.3
# Room that a cell label needs around the cell centre; cells without it get no label.
LABEL_HALF_WIDTH_DEGREES = 0.3
LABEL_HALF_HEIGHT_DEGREES = 0.15
CHART_FILE_NAME = "alert_rules_example"


def main() -> None:
    alerts = _load_pre_season_alerts()
    _print_agreement(alerts)

    region_season = next(
        region_season
        for region_season in REGION_SEASONS
        if region_season.name == EXAMPLE_REGION_SEASON_NAME
    )
    forecast = alerts.loc[
        (alerts["region_season"] == region_season.name)
        & (alerts["season_year"] == EXAMPLE_SEASON_YEAR)
    ].iloc[0]
    rainfall = load_rainfall()[region_season.region_key]
    region = shape(load_region_geometries()[region_season.region_key])

    figure = Figure(figsize=(11, 5.8), layout="constrained")
    region_axis, area_axis = figure.subplots(1, 2)
    _draw_region_rule(region_axis, region, forecast)
    _draw_area_rule(
        area_axis, region, rainfall, _get_example_cell_shares(region_season, rainfall)
    )
    _finish_figure(figure, region_season, forecast)


def _load_pre_season_alerts() -> pd.DataFrame:
    alerts = pd.read_csv(FORECAST_ALERTS_FILE)
    return alerts.loc[
        (alerts["variant"] == ForecastVariant.REST_OF_SEASON.value)
        & (alerts["months_until_season_start"] == EXAMPLE_MONTHS_BEFORE_SEASON)
    ]


def _print_agreement(alerts: pd.DataFrame) -> None:
    pooled_alerts = alerts.loc[
        alerts["region_season"].isin(
            [region_season.name for region_season in POOLED_REGION_SEASONS]
        )
    ]
    region_rule_column = get_probability_alert_column(DEFAULT_PROBABILITY_THRESHOLD)
    is_same = pooled_alerts[region_rule_column].astype(str) == pooled_alerts[
        AREA_RULE_ALERT_COLUMN
    ].astype(str)
    print(
        f"The rules agree on {is_same.sum()} of {len(pooled_alerts)} forecasts "
        f"({is_same.mean():.0%}), {EXAMPLE_MONTHS_BEFORE_SEASON} month(s) before the season"
    )


def _get_example_cell_shares(
    region_season: RegionSeason, rainfall: RegionRainfall
) -> np.ndarray:
    season_years, cell_shares = calculate_cell_shares_of_dry_members(
        region_season, rainfall, EXAMPLE_MONTHS_BEFORE_SEASON
    )
    return cell_shares[season_years == EXAMPLE_SEASON_YEAR][0]


def _draw_region_rule(axis: Axes, region: BaseGeometry, forecast: pd.Series) -> None:
    share = forecast["probability_below_lower_tercile"]
    is_alert = share >= DEFAULT_PROBABILITY_THRESHOLD
    axis.add_patch(
        PathPatch(
            _to_path(region),
            facecolor=_get_fill_colour(is_alert),
            edgecolor=OUTLINE_COLOUR,
            linewidth=1,
        )
    )
    centre = region.representative_point()
    axis.annotate(
        f"{share:.0%}",
        (centre.x, centre.y),
        horizontalalignment="center",
        verticalalignment="center",
        fontsize="xx-large",
        fontweight="bold",
        color=_get_text_colour(is_alert),
    )
    dry_member_count = round(share * forecast["member_count"])
    _style_map(
        axis,
        region,
        title="Region-average rule",
        explanation=(
            "1. Average the rainfall over the region\n2. Count the dry members"
        ),
        result=(
            f"{dry_member_count} of {forecast['member_count']} members dry ({share:.0%})\n"
            f"{_describe_outcome(is_alert, DEFAULT_PROBABILITY_THRESHOLD)}"
        ),
    )


def _draw_area_rule(
    axis: Axes, region: BaseGeometry, rainfall: RegionRainfall, cell_shares: np.ndarray
) -> None:
    outline = PathPatch(
        _to_path(region), facecolor="none", edgecolor=OUTLINE_COLOUR, linewidth=1
    )
    axis.add_patch(outline)
    is_dry_cell = cell_shares >= AREA_RULE_MINIMUM_PROBABILITY
    for latitude, longitude, share, is_dry in zip(
        rainfall.cell_latitudes,
        rainfall.cell_longitudes,
        cell_shares,
        is_dry_cell,
        strict=True,
    ):
        half_cell = SEAS5_CELL_SIZE_DEGREES / 2
        cell = Rectangle(
            (longitude - half_cell, latitude - half_cell),
            SEAS5_CELL_SIZE_DEGREES,
            SEAS5_CELL_SIZE_DEGREES,
            facecolor=_get_fill_colour(is_dry),
            edgecolor="white",
            linewidth=1,
        )
        axis.add_patch(cell)
        cell.set_clip_path(outline)
        if _has_room_for_label(region, latitude, longitude):
            axis.annotate(
                f"{share:.0%}",
                (longitude, latitude),
                horizontalalignment="center",
                verticalalignment="center",
                fontsize="x-small",
                color=_get_text_colour(is_dry),
            )
    area_share = (
        is_dry_cell * rainfall.cell_weights
    ).sum() / rainfall.cell_weights.sum()
    _style_map(
        axis,
        region,
        title="Grid-cell rule (IBF v1 style)",
        explanation=(
            "1. Count the dry members per grid cell\n"
            "2. Add up the area of the dry cells"
        ),
        result=(
            f"Dry cells cover {area_share:.0%} of the region\n"
            f"{_describe_outcome(area_share >= AREA_RULE_MINIMUM_AREA_SHARE, AREA_RULE_MINIMUM_AREA_SHARE)}"
        ),
    )


def _has_room_for_label(
    region: BaseGeometry, latitude: float, longitude: float
) -> bool:
    return region.contains(
        box(
            longitude - LABEL_HALF_WIDTH_DEGREES,
            latitude - LABEL_HALF_HEIGHT_DEGREES,
            longitude + LABEL_HALF_WIDTH_DEGREES,
            latitude + LABEL_HALF_HEIGHT_DEGREES,
        )
    )


def _describe_outcome(is_alert: bool, threshold: float) -> str:
    if is_alert:
        return f"At least {threshold:.0%}: alert"
    return f"Below {threshold:.0%}: no alert"


def _get_fill_colour(is_dry: bool) -> str:
    return DRY_COLOUR if is_dry else NOT_DRY_COLOUR


def _get_text_colour(is_dry: bool) -> str:
    return TEXT_ON_DRY_COLOUR if is_dry else TEXT_ON_NOT_DRY_COLOUR


def _to_path(geometry: BaseGeometry) -> Path:
    polygons = getattr(geometry, "geoms", [geometry])
    rings = [
        np.asarray(ring.coords)[:, :2]
        for polygon in polygons
        for ring in (polygon.exterior, *polygon.interiors)
    ]
    return Path.make_compound_path(*[Path(ring, closed=True) for ring in rings])


def _style_map(
    axis: Axes, region: BaseGeometry, title: str, explanation: str, result: str
) -> None:
    west, south, east, north = region.bounds
    axis.set_xlim(west - MAP_MARGIN_DEGREES, east + MAP_MARGIN_DEGREES)
    axis.set_ylim(south - MAP_MARGIN_DEGREES, north + MAP_MARGIN_DEGREES)
    # A degree of longitude is shorter than a degree of latitude away from the equator.
    axis.set_aspect(1 / math.cos(math.radians((south + north) / 2)))
    axis.set_axis_off()
    axis.set_title(
        f"{title}\n\n", loc="left", fontsize="large", fontweight="bold", pad=10
    )
    axis.text(
        0,
        1,
        explanation,
        transform=axis.transAxes,
        verticalalignment="bottom",
        fontsize="medium",
        color=NEUTRAL_COLOUR,
        linespacing=1.4,
    )
    axis.text(
        0.5,
        -0.02,
        result,
        transform=axis.transAxes,
        horizontalalignment="center",
        verticalalignment="top",
        fontsize="large",
        fontweight="bold",
        linespacing=1.4,
    )


def _finish_figure(
    figure: Figure, region_season: RegionSeason, forecast: pd.Series
) -> None:
    figure.legend(
        handles=[
            Patch(
                facecolor=DRY_COLOUR,
                label=f"At least {AREA_RULE_MINIMUM_PROBABILITY:.0%} of members dry",
            ),
            Patch(facecolor=NOT_DRY_COLOUR, label="Fewer members dry"),
        ],
        title=(
            f"{region_season.name} {EXAMPLE_SEASON_YEAR}, forecast issued in "
            f"{calendar.month_name[int(forecast.at['run_month'])]}; "
            "dry = rainfall in the driest third of the hindcast"
        ),
        alignment="left",
        loc="outside upper left",
        ncols=2,
        frameon=False,
        fontsize="small",
    )
    save_figure(figure, CHART_FILE_NAME)


if __name__ == "__main__":
    main()
