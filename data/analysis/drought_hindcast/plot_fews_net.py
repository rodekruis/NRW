"""Draw the FEWS NET classifications over time, the skill of the FEWS NET alerts next to
SEAS5, and what the classifications show around the end of drought seasons."""

import pandas as pd
from analysis.drought_hindcast.calculate_fews_net_alerts import (
    CURRENT_SITUATION_SCENARIO,
    load_region_phases,
    REPORT_MONTH_COLUMN,
)
from analysis.drought_hindcast.calculate_fews_net_skill import (
    POOLED_FEWS_NET_REGION_SEASONS,
)
from analysis.drought_hindcast.calculate_skill import (
    to_booleans,
    UNCERTAINTY_PERCENTILES,
)
from analysis.drought_hindcast.check_fews_net import NEAR_TERM_SCENARIO
from analysis.drought_hindcast.combine_indicators import Combination
from analysis.drought_hindcast.definitions import (
    get_observed_drought_column,
    REGION_SEASONS,
)
from analysis.drought_hindcast.indicator_charts import (
    add_legend,
    create_panels,
    SEAS5_COLOUR,
    set_lead_time_axis,
)
from analysis.drought_hindcast.indicator_data import (
    FEWS_NET_AROUND_SEASON_END_FILE,
    FEWS_NET_SKILL_FILE,
)
from analysis.drought_hindcast.indicator_definitions import (
    FewsNetAlertRule,
    Indicator,
    MAIN_FEWS_NET_ALERT_RULE,
    MAIN_FEWS_NET_REPORT_LAG_MONTHS,
)
from analysis.drought_hindcast.plot_skill import (
    DEFAULT_DROUGHT_DEFINITION,
    draw_measures,
    DROUGHT_DEFINITION_LABELS,
    FALSE_ALARM_RATIO_COLOUR,
    GRID_COLOUR,
    HIT_RATE_COLOUR,
    LEAD_TIME_MEASURE_OFFSET,
    MEASURE_COLOURS,
    MEASURE_LABELS,
    NEUTRAL_COLOUR,
    NO_SKILL_LINE_STYLE,
    RANGE_OPACITY,
    save_figure,
    style_percent_axis,
)
from analysis.drought_hindcast.prepare_fews_net import CRISIS_OR_WORSE_COLUMN
from analysis.drought_hindcast.prepare_iod import MONTH_FREQUENCY
from analysis.drought_hindcast.study_area import OBSERVED_SEASONS_FILE
from matplotlib.dates import DateFormatter, YearLocator
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import PercentFormatter

DROUGHT_LABEL = DROUGHT_DEFINITION_LABELS[DEFAULT_DROUGHT_DEFINITION].lower()
SHARE_LABEL = "Share of the region in Phase 3 or worse"
REGION_COLUMN_COUNT = 4
REGION_FIGURE_WIDTH_INCHES = 10.5
REGION_PANEL_HEIGHT_INCHES = 2.1
SKILL_FIGURE_WIDTH_INCHES = 11.5
YEAR_TICK_STEP = 4
DROUGHT_SEASON_OPACITY = 0.18
AROUND_SEASON_END_FIGURE_WIDTH_INCHES = 9
# Panel titles of the alerts in the skill chart.
SKILL_PANELS: dict[tuple[str, str | None], str] = {
    (Indicator.SEAS5.value, None): "SEAS5, 40% of members dry",
    (
        Indicator.FEWS_NET.value,
        FewsNetAlertRule.OWN_TERCILE.value,
    ): "FEWS NET: high share",
    (
        Indicator.FEWS_NET.value,
        FewsNetAlertRule.WORSENING.value,
    ): "FEWS NET: worsening",
    (Combination.EITHER.value, MAIN_FEWS_NET_ALERT_RULE.value): "Either",
}


def main() -> None:
    _plot_shares_by_region()
    _plot_skill()
    _plot_around_season_end()


def _plot_shares_by_region() -> None:
    """Per region, the share in Phase 3 or worse over time, with the observed droughts."""
    phases = load_region_phases()
    observed = pd.read_csv(OBSERVED_SEASONS_FILE)
    region_keys = list(
        dict.fromkeys(region_season.region_key for region_season in REGION_SEASONS)
    )
    figure, axes = create_panels(
        row_count=-(-len(region_keys) // REGION_COLUMN_COUNT),
        column_count=REGION_COLUMN_COUNT,
        figure_width_inches=REGION_FIGURE_WIDTH_INCHES,
        panel_height_inches=REGION_PANEL_HEIGHT_INCHES,
    )
    panels = [axis for row in axes for axis in row]
    for unused_panel in panels[len(region_keys) :]:
        unused_panel.set_visible(False)
    first_month = phases[REPORT_MONTH_COLUMN].min()
    last_month = phases[REPORT_MONTH_COLUMN].max()
    for axis, region_key in zip(panels, region_keys, strict=False):
        region_phases = phases.loc[phases["region_key"] == region_key]
        for region_season in REGION_SEASONS:
            if (
                region_season.region_key != region_key
                or not region_season.is_in_pooled_results
            ):
                continue
            seasons = observed.loc[observed["region_season"] == region_season.name]
            is_drought = to_booleans(
                seasons, get_observed_drought_column(DEFAULT_DROUGHT_DEFINITION)
            )
            for season_year in seasons.loc[is_drought, "season_year"]:
                season_start = pd.Period(
                    year=int(season_year),
                    month=region_season.months[0],
                    freq=MONTH_FREQUENCY,
                )
                if season_start < first_month:
                    continue
                axis.axvspan(
                    season_start.to_timestamp(),
                    (season_start + len(region_season.months)).to_timestamp(),
                    color=FALSE_ALARM_RATIO_COLOUR,
                    alpha=DROUGHT_SEASON_OPACITY,
                    linewidth=0,
                )
        near_term = region_phases.loc[region_phases["scenario"] == NEAR_TERM_SCENARIO]
        axis.plot(
            near_term[REPORT_MONTH_COLUMN].dt.to_timestamp(),
            near_term[CRISIS_OR_WORSE_COLUMN],
            color=HIT_RATE_COLOUR,
            linewidth=1.2,
        )
        current = region_phases.loc[
            region_phases["scenario"] == CURRENT_SITUATION_SCENARIO
        ]
        axis.scatter(
            current[REPORT_MONTH_COLUMN].dt.to_timestamp(),
            current[CRISIS_OR_WORSE_COLUMN],
            color=SEAS5_COLOUR,
            s=8,
            zorder=3,
        )
        style_percent_axis(axis, region_key)
        axis.set_xlim(first_month.to_timestamp(), (last_month + 1).to_timestamp())
        axis.xaxis.set_major_locator(YearLocator(YEAR_TICK_STEP))
        axis.xaxis.set_major_formatter(DateFormatter("%Y"))
    figure.supylabel(SHARE_LABEL, fontsize="medium")
    add_legend(
        figure,
        [
            Line2D(
                [],
                [],
                color=SEAS5_COLOUR,
                linestyle="",
                marker="o",
                markersize=4,
                label="Current situation",
            ),
            Line2D([], [], color=HIT_RATE_COLOUR, label="Near-term projection"),
            Patch(
                color=FALSE_ALARM_RATIO_COLOUR,
                alpha=DROUGHT_SEASON_OPACITY,
                label=f"Observed drought season ({DROUGHT_LABEL})",
            ),
        ],
        "FEWS NET classifications per region, by report month",
        x_label="",
    )
    save_figure(figure, "fews_net_shares_by_region")


def _plot_skill() -> None:
    """Hit rate and false-alarm ratio per lead time: SEAS5 on the FEWS NET seasons, the
    FEWS NET alerts, and either."""
    skill = pd.read_csv(FEWS_NET_SKILL_FILE)
    skill = skill.loc[
        (skill["scope"] == POOLED_FEWS_NET_REGION_SEASONS)
        & (skill["report_lag_months"] == MAIN_FEWS_NET_REPORT_LAG_MONTHS)
        & (skill["drought_definition"] == DEFAULT_DROUGHT_DEFINITION)
    ]
    figure, axes = create_panels(
        row_count=1,
        column_count=len(SKILL_PANELS),
        figure_width_inches=SKILL_FIGURE_WIDTH_INCHES,
    )
    for axis, ((indicator, alert_rule), title) in zip(
        axes[0], SKILL_PANELS.items(), strict=True
    ):
        scores = skill.loc[
            (skill["indicator"] == indicator)
            & ((skill["alert_rule"] == alert_rule) | (alert_rule is None))
        ].sort_values("months_until_season_start", ascending=False)
        draw_measures(
            axis, scores["months_until_season_start"], scores, LEAD_TIME_MEASURE_OFFSET
        )
        style_percent_axis(axis, title)
        set_lead_time_axis(axis)
    low_percentile, high_percentile = UNCERTAINTY_PERCENTILES
    add_legend(
        figure,
        [
            *[
                Line2D(
                    [],
                    [],
                    color=MEASURE_COLOURS[measure],
                    linewidth=2,
                    marker="o",
                    label=label,
                )
                for measure, label in MEASURE_LABELS.items()
            ],
            Line2D(
                [],
                [],
                color=NEUTRAL_COLOUR,
                alpha=RANGE_OPACITY,
                linestyle="",
                marker="|",
                markersize=14,
                markeredgewidth=1.5,
                label=f"{high_percentile - low_percentile:.0f}% range",
            ),
            Line2D(
                [],
                [],
                color=NEUTRAL_COLOUR,
                linestyle=NO_SKILL_LINE_STYLE,
                linewidth=1,
                label="Level without skill",
            ),
        ],
        f"{POOLED_FEWS_NET_REGION_SEASONS}, seasons from 2011; {DROUGHT_LABEL}",
    )
    save_figure(figure, "fews_net_skill")


def _plot_around_season_end() -> None:
    """The near-term share against its usual level, month by month around the season end,
    for drought seasons and for other seasons."""
    around_season_end = pd.read_csv(FEWS_NET_AROUND_SEASON_END_FILE)
    pooled = around_season_end.loc[
        around_season_end["scope"] == POOLED_FEWS_NET_REGION_SEASONS
    ]
    figure, axes = create_panels(
        row_count=1,
        column_count=1,
        figure_width_inches=AROUND_SEASON_END_FIGURE_WIDTH_INCHES,
    )
    axis = axes[0][0]
    months = pooled["months_after_season_end"]
    lines = {
        "Drought seasons": (
            "mean_share_anomaly_of_droughts",
            FALSE_ALARM_RATIO_COLOUR,
        ),
        "Other seasons": ("mean_share_anomaly_of_other_seasons", NEUTRAL_COLOUR),
    }
    for column, colour in lines.values():
        axis.plot(months, pooled[column], color=colour, linewidth=2, marker="o")
    axis.axhline(0, color=NEUTRAL_COLOUR, linewidth=1)
    # The season ends between its last month and the month after it.
    axis.axvline(0.5, color=NEUTRAL_COLOUR, linestyle=NO_SKILL_LINE_STYLE, linewidth=1)
    axis.set_xticks(months)
    axis.yaxis.set_major_formatter(PercentFormatter(xmax=1, decimals=0))
    axis.grid(axis="y", color=GRID_COLOUR)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)
    axis.tick_params(length=0)
    axis.set_ylabel(f"{SHARE_LABEL},\nagainst the usual share")
    add_legend(
        figure,
        [
            *[
                Line2D([], [], color=colour, linewidth=2, marker="o", label=label)
                for label, (_, colour) in lines.items()
            ],
            Line2D(
                [],
                [],
                color=NEUTRAL_COLOUR,
                linestyle=NO_SKILL_LINE_STYLE,
                label="End of the season",
            ),
        ],
        f"Near-term projection of the latest report; {POOLED_FEWS_NET_REGION_SEASONS}; "
        f"{DROUGHT_LABEL}",
        x_label="Months after the last month of the season",
    )
    save_figure(figure, "fews_net_around_season_end")


if __name__ == "__main__":
    main()
