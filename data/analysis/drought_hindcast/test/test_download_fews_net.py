import os
from datetime import datetime, UTC
from pathlib import Path

import pytest
from analysis.drought_hindcast.download_fews_net import is_final

YEAR = 2024


@pytest.mark.parametrize(
    ("downloaded_at", "expected"),
    [
        (datetime(2024, 11, 16, tzinfo=UTC), False),
        (datetime(2025, 1, 15, tzinfo=UTC), False),
        (datetime(2025, 6, 1, tzinfo=UTC), True),
    ],
)
def test_a_year_is_final_when_downloaded_well_after_its_end(
    tmp_path: Path, downloaded_at: datetime, expected: bool
) -> None:
    # Arrange
    path = tmp_path / f"KEN_{YEAR}.csv.gz"
    path.write_bytes(b"")
    os.utime(path, (downloaded_at.timestamp(), downloaded_at.timestamp()))

    # Act
    result = is_final(path, YEAR)

    # Assert
    assert result is expected


def test_a_year_that_is_not_downloaded_is_not_final(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / f"KEN_{YEAR}.csv.gz"

    # Act
    result = is_final(path, YEAR)

    # Assert
    assert result is False
