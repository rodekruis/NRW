import pandas as pd
from analysis.drought_hindcast.definitions import get_observed_drought_column
from analysis.drought_hindcast.plot_skill import DEFAULT_DROUGHT_DEFINITION
from analysis.drought_hindcast.plot_threshold_steps import (
    format_band,
    summarise_threshold_bands,
)

MEMBER_COUNT = 25


def test_each_forecast_counts_in_the_band_of_the_highest_threshold_it_reaches() -> None:
    # Arrange
    # 10 of 25 members is exactly 40%, so it reaches that threshold.
    cases = pd.DataFrame(
        {
            "months_until_season_start": 1,
            "probability_below_lower_tercile": [0.72, 0.4, 0.4, 0.36, 0.32, 0.28, 0.0],
            "member_count": MEMBER_COUNT,
            get_observed_drought_column(DEFAULT_DROUGHT_DEFINITION): [
                True,
                True,
                False,
                True,
                False,
                False,
                False,
            ],
        }
    )

    # Act
    bands = summarise_threshold_bands(cases)

    # Assert
    assert [
        format_band(lower_threshold, upper_threshold)
        for lower_threshold, upper_threshold in zip(
            bands["lower_threshold"], bands["upper_threshold"], strict=True
        )
    ] == ["60% or more", "50–60%", "40–50%", "30–40%", "Below 30%"]
    assert bands["forecast_count"].tolist() == [1, 0, 2, 2, 2]
    assert bands["false_alarm_count"].tolist() == [0, 0, 1, 1, 2]
    assert bands["false_alarm_ratio"].iloc[2] == 0.5
    assert pd.isna(bands["false_alarm_ratio"].iloc[1])
    assert bands["false_alarm_ratio_without_skill"].unique().tolist() == [0.571]
