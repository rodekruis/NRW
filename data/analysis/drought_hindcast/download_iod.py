"""Download the observed Indian Ocean Dipole index (Dipole Mode Index) from each candidate source."""

from enum import StrEnum
from pathlib import Path

import requests
from analysis.drought_hindcast.indicator_data import IOD_DIRECTORY


class IodSource(StrEnum):
    """Named after the sea surface temperature dataset the index is calculated from."""

    HADISST = "hadisst"
    ERSST = "ersst"
    OISST_WEEKLY = "oisst_weekly"
    OISST_JAMSTEC = "oisst_jamstec"


IOD_SOURCE_URLS: dict[IodSource, str] = {
    # NOAA Physical Sciences Laboratory, monthly from 1870.
    IodSource.HADISST: "https://psl.noaa.gov/gcos_wgsp/Timeseries/Data/dmi.had.long.data",
    # NOAA Climate Prediction Center, monthly from 1950.
    IodSource.ERSST: (
        "https://www.cpc.ncep.noaa.gov/products/international/ocean_monitoring/IODMI/"
        "mnth.ersstv6.clim19912020.dmi_current.txt"
    ),
    # NOAA Ocean Observations Panel for Climate, weekly from 1981-09.
    IodSource.OISST_WEEKLY: "https://stateoftheocean.osmc.noaa.gov/sur/data/dmi.nc",
    # JAMSTEC, monthly from 1982, in one file with its SINTEX-F forecasts.
    IodSource.OISST_JAMSTEC: (
        "https://www.jamstec.go.jp/virtualearth/data/SINTEX/SINTEX_DMI.csv"
    ),
}
REQUEST_TIMEOUT_SECONDS = 120


def main() -> None:
    IOD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    # The files are small and grow every month, so each run replaces them.
    for source, url in IOD_SOURCE_URLS.items():
        response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        path = get_iod_file(source)
        path.write_bytes(response.content)
        print(f"Downloaded {source} to {path.name}")
    print(f"IOD complete in {IOD_DIRECTORY}")


def get_iod_file(source: IodSource) -> Path:
    return IOD_DIRECTORY / IOD_SOURCE_URLS[source].rsplit("/", maxsplit=1)[-1]


if __name__ == "__main__":
    main()
