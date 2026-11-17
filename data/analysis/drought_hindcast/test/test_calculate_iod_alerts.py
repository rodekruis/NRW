import numpy as np
import pandas as pd
import pytest
from analysis.drought_hindcast.calculate_iod_alerts import (
    calculate_leave_one_out_quantile,
    calculate_run_month_alerts,
)
from analysis.drought_hindcast.indicator_definitions import (
    get_iod_alert_column,
    IOD_EVENT_THRESHOLD,
    IodAlertRule,
    IodPhase,
)

JANUARY = 1
OCTOBER = 10


def _build_monthly_index(first_month: str, values: list[float]) -> pd.Series:
    return pd.Series(
        values, index=pd.period_range(first_month, periods=len(values), freq="M")
    )


def test_index_of_a_run_is_the_average_of_the_months_before_the_run_month() -> None:
    # Arrange
    monthly_index = _build_monthly_index("2024-06", [0.1, 0.2, 0.3, 0.6, 9.0])

    # Act
    runs = calculate_run_month_alerts(
        monthly_index,
        first_season_month=JANUARY,
        drought_phase=IodPhase.POSITIVE,
        months_until_season_start=3,
        index_month_count=4,
    )

    # Assert
    # The October 2024 run, for the season that starts in January 2025, sees June to September.
    assert runs[["season_year", "run_year", "run_month"]].to_dict("records") == [
        {"season_year": 2025, "run_year": 2024, "run_month": OCTOBER}
    ]
    assert runs["iod_index"].iloc[0] == pytest.approx(0.3)
    # A single season has no other years to take its own tercile from.
    assert not runs[get_iod_alert_column(IodAlertRule.OWN_TERCILE)].iloc[0]


def test_a_run_without_every_month_of_its_index_is_left_out() -> None:
    # Arrange
    monthly_index = _build_monthly_index("2024-07", [0.2, 0.3, 0.6])

    # Act
    runs = calculate_run_month_alerts(
        monthly_index,
        first_season_month=JANUARY,
        drought_phase=IodPhase.POSITIVE,
        months_until_season_start=3,
        index_month_count=4,
    )

    # Assert
    assert runs.empty


@pytest.mark.parametrize(
    ("drought_phase", "expected_alert_years"),
    [(IodPhase.POSITIVE, [2023]), (IodPhase.NEGATIVE, [2021])],
)
def test_alerts_are_for_the_outer_third_towards_the_drought_phase(
    drought_phase: IodPhase, expected_alert_years: list[int]
) -> None:
    # Arrange
    september_index_by_year = {2021: -0.9, 2022: 0.0, 2023: 0.8, 2024: 0.1}
    monthly_index = pd.Series(
        {
            pd.Period(year=year, month=9, freq="M"): index
            for year, index in september_index_by_year.items()
        }
    )

    # Act
    runs = calculate_run_month_alerts(
        monthly_index,
        first_season_month=OCTOBER,
        drought_phase=drought_phase,
        months_until_season_start=0,
        index_month_count=1,
    )

    # Assert
    for rule in IodAlertRule:
        is_alert = runs[get_iod_alert_column(rule)]
        assert runs.loc[is_alert, "season_year"].tolist() == expected_alert_years
    assert max(september_index_by_year.values()) >= IOD_EVENT_THRESHOLD


def test_leave_one_out_quantile_ignores_the_value_itself() -> None:
    # Arrange
    values = np.array([0.0, 1.0, 100.0])

    # Act
    medians = calculate_leave_one_out_quantile(values, quantile=0.5)

    # Assert
    assert medians == pytest.approx([50.5, 50.0, 0.5])
