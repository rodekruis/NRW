"""Combine the Indian Ocean Dipole index of every source into one monthly table."""

import re
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import xarray as xr
from analysis.drought_hindcast.download_iod import get_iod_file, IodSource
from analysis.drought_hindcast.indicator_data import IOD_MONTHLY_FILE
from analysis.drought_hindcast.study_area import FIRST_YEAR

MONTH_FREQUENCY = "M"
ERSST_ROW_PATTERN = re.compile(
    r"^\s*(?P<year>\d{4})\s+(?P<month>\d{1,2})\s+\S+\s+\S+\s+(?P<index>-?\d+\.\d+)\s*$",
    re.MULTILINE,
)
OISST_WEEKLY_VARIABLE = "DMI"
# A month holds four or five weekly values; fewer means it is not complete yet.
MINIMUM_WEEKS_PER_MONTH = 4
JAMSTEC_MONTH_COLUMN = "time"
JAMSTEC_OBSERVED_COLUMN = "Obs"
# The sources publish two or three decimals.
OUTPUT_FLOAT_FORMAT = "%.3f"


def main() -> None:
    iod = pd.DataFrame(
        {
            get_iod_column(source): parse(get_iod_file(source))
            for source, parse in PARSERS.items()
        }
    ).sort_index()
    iod = iod[iod.index.year >= FIRST_YEAR]
    iod.index.name = "month"

    IOD_MONTHLY_FILE.parent.mkdir(parents=True, exist_ok=True)
    iod.to_csv(IOD_MONTHLY_FILE, float_format=OUTPUT_FLOAT_FORMAT)
    for column in iod.columns:
        months = iod[column].dropna().index
        print(f"{column}: {len(months)} months, {months[0]} to {months[-1]}")
    print("Correlation between sources:")
    print(iod.corr().round(2).to_string())
    print(f"Wrote {len(iod)} months to {IOD_MONTHLY_FILE}")


def get_iod_column(source: IodSource) -> str:
    return f"iod_{source}"


def parse_hadisst(path: Path) -> pd.Series:
    """One row per year with twelve values, between the year range and the missing value."""
    lines = path.read_text(encoding="utf-8").splitlines()
    first_year, last_year = (int(value) for value in lines[0].split())
    year_lines = lines[1 : last_year - first_year + 2]
    missing_value = float(lines[len(year_lines) + 1])

    index_by_month: dict[pd.Period, float] = {}
    for line in year_lines:
        year, *monthly_values = line.split()
        for month, value in enumerate(monthly_values, start=1):
            index_by_month[_get_month(int(year), month)] = float(value)
    index = pd.Series(index_by_month)
    return index[index != missing_value]


def parse_ersst(path: Path) -> pd.Series:
    """One row per month: year, month, western pole, eastern pole and their difference."""
    return pd.Series(
        {
            _get_month(int(row["year"]), int(row["month"])): float(row["index"])
            for row in ERSST_ROW_PATTERN.finditer(path.read_text(encoding="utf-8"))
        }
    )


def parse_oisst_weekly(path: Path) -> pd.Series:
    """Weekly values, averaged over the weeks that start in each month."""
    with xr.open_dataset(path) as dataset:
        weekly_index = dataset[OISST_WEEKLY_VARIABLE].to_series()
    weeks_by_month = weekly_index.groupby(
        pd.DatetimeIndex(weekly_index.index).to_period(MONTH_FREQUENCY)
    )
    return weeks_by_month.mean()[weeks_by_month.count() >= MINIMUM_WEEKS_PER_MONTH]


def parse_oisst_jamstec(path: Path) -> pd.Series:
    """One row per month; the forecast months after the last observation have no observed value."""
    observed = pd.read_csv(
        path,
        usecols=[JAMSTEC_MONTH_COLUMN, JAMSTEC_OBSERVED_COLUMN],
        parse_dates=[JAMSTEC_MONTH_COLUMN],
    ).dropna()
    return pd.Series(
        observed[JAMSTEC_OBSERVED_COLUMN].to_numpy(),
        index=pd.PeriodIndex(observed[JAMSTEC_MONTH_COLUMN], freq=MONTH_FREQUENCY),
    )


def _get_month(year: int, month: int) -> pd.Period:
    return pd.Period(year=year, month=month, freq=MONTH_FREQUENCY)


PARSERS: dict[IodSource, Callable[[Path], pd.Series]] = {
    IodSource.HADISST: parse_hadisst,
    IodSource.ERSST: parse_ersst,
    IodSource.OISST_WEEKLY: parse_oisst_weekly,
    IodSource.OISST_JAMSTEC: parse_oisst_jamstec,
}


if __name__ == "__main__":
    main()
