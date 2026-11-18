"""Run the steps of the analysis in the order in which they depend on each other.

Without options: every step from the downloaded data to the tables and charts. With
`--collect-data`: first build the region shapes and download the data. Both need a local
clone of the seed-data repo.
"""

import argparse
from collections.abc import Callable

from analysis.drought_hindcast import (
    build_region_shapes,
    calculate_alerts,
    calculate_fews_net_alerts,
    calculate_fews_net_skill,
    calculate_iod_alerts,
    calculate_iod_skill,
    calculate_skill,
    check_against_raw_data,
    check_fews_net,
    check_kenya_region,
    check_skill,
    combine_indicators,
    compare_fews_net_with_skill_review,
    compare_outcomes,
    compare_with_earlier_matrix,
    compare_with_skill_review,
    download_chirps,
    download_fews_net,
    download_iod,
    download_seas5,
    plot_alert_rules,
    plot_countries,
    plot_fews_net,
    plot_in_season,
    plot_iod,
    plot_skill,
    plot_threshold_choices,
    plot_threshold_steps,
    plot_thresholds,
    prepare_fews_net,
    prepare_forecast_rainfall,
    prepare_iod,
    prepare_observed_rainfall,
)

Step = Callable[[], None]

# These need the internet and a Copernicus CDS account. The downloads take their extent
# from the region shapes, and skip what is already there.
DATA_COLLECTION_STEPS: tuple[Step, ...] = (
    build_region_shapes.main,
    download_chirps.main,
    download_seas5.main,
    download_iod.main,
    download_fews_net.main,
)
ANALYSIS_STEPS: tuple[Step, ...] = (
    prepare_observed_rainfall.main,
    prepare_forecast_rainfall.main,
    prepare_iod.main,
    prepare_fews_net.main,
    # SEAS5
    calculate_alerts.main,
    calculate_skill.main,
    plot_skill.main,
    plot_alert_rules.main,
    plot_thresholds.main,
    plot_threshold_steps.main,
    plot_threshold_choices.main,
    plot_in_season.main,
    check_skill.main,
    compare_with_earlier_matrix.main,
    compare_with_skill_review.main,
    plot_countries.main,
    check_against_raw_data.main,
    # IOD
    calculate_iod_alerts.main,
    calculate_iod_skill.main,
    combine_indicators.main,
    plot_iod.main,
    # FEWS NET
    calculate_fews_net_alerts.main,
    calculate_fews_net_skill.main,
    check_fews_net.main,
    compare_outcomes.main,
    plot_fews_net.main,
    check_kenya_region.main,
    compare_fews_net_with_skill_review.main,
)


def main() -> None:
    arguments = _parse_arguments()
    steps = select_steps(arguments.collect_data, arguments.from_step)
    for position, step in enumerate(steps, start=1):
        print(f"\n[{position}/{len(steps)}] {get_step_name(step)}", flush=True)
        step()


def select_steps(collects_data: bool, first_step_name: str | None) -> tuple[Step, ...]:
    """The steps to run, from `first_step_name` on when it is given."""
    steps = (
        (*DATA_COLLECTION_STEPS, *ANALYSIS_STEPS) if collects_data else ANALYSIS_STEPS
    )
    if first_step_name is None:
        return steps
    step_names = [get_step_name(step) for step in steps]
    if first_step_name not in step_names:
        raise ValueError(
            f"No step {first_step_name} among the steps to run: {', '.join(step_names)}"
        )
    return steps[step_names.index(first_step_name) :]


def get_step_name(step: Step) -> str:
    return step.__module__.rsplit(".", maxsplit=1)[-1]


def _parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collect-data",
        action="store_true",
        help="First build the region shapes and download the data.",
    )
    parser.add_argument(
        "--from-step",
        help="Start at this step, to resume a run. For example: calculate_alerts.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    main()
