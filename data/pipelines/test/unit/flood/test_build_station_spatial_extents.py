import json

from data_management.seed_data_management.flood.build_station_spatial_extents import (
    Basin,
    build_spatial_extents,
    StationSpatialExtent,
    trace_station_basins,
    write_spatial_extents,
)
from shapely.geometry import box, Point

RIVER_END = 0


def create_river_basins() -> dict[int, Basin]:
    """Four square basins in a row; the river runs from basin 1 to basin 4."""
    return {
        basin_id: Basin(
            next_down_id=next_down_id,
            distance_to_river_end_km=distance_to_river_end_km,
            geometry=box(basin_id - 1, 0, basin_id, 1),
        )
        for basin_id, next_down_id, distance_to_river_end_km in [
            (1, 2, 300.0),
            (2, 3, 200.0),
            (3, 4, 100.0),
            (4, RIVER_END, 0.0),
        ]
    }


def test_trace_follows_the_river_up_to_the_distance_limit():
    # Arrange
    station_points = {"UPSTREAM": Point(0.5, 0.5)}

    # Act
    chains = trace_station_basins(
        station_points, create_river_basins(), downstream_distance_km=150.0
    )

    # Assert
    assert chains == {"UPSTREAM": [1, 2]}


def test_trace_runs_to_the_end_of_the_river_within_the_distance_limit():
    # Arrange
    station_points = {"UPSTREAM": Point(0.5, 0.5)}

    # Act
    chains = trace_station_basins(
        station_points, create_river_basins(), downstream_distance_km=1000.0
    )

    # Assert
    assert chains == {"UPSTREAM": [1, 2, 3, 4]}


def test_trace_stops_before_a_basin_with_another_station():
    # Arrange
    station_points = {"UPSTREAM": Point(0.5, 0.5), "DOWNSTREAM": Point(2.5, 0.5)}

    # Act
    chains = trace_station_basins(
        station_points, create_river_basins(), downstream_distance_km=1000.0
    )

    # Assert
    assert chains == {"UPSTREAM": [1, 2], "DOWNSTREAM": [3, 4]}


def test_stations_in_the_same_basin_get_the_same_trace():
    # Arrange
    station_points = {"FIRST": Point(0.2, 0.5), "SECOND": Point(0.8, 0.5)}

    # Act
    chains = trace_station_basins(
        station_points, create_river_basins(), downstream_distance_km=150.0
    )

    # Assert
    assert chains == {"FIRST": [1, 2], "SECOND": [1, 2]}


def test_station_outside_every_basin_gets_no_trace():
    # Arrange
    station_points = {"AT_SEA": Point(10.0, 10.0)}

    # Act
    chains = trace_station_basins(
        station_points, create_river_basins(), downstream_distance_km=150.0
    )

    # Assert
    assert chains == {}


def test_spatial_extent_is_clipped_to_the_country():
    # Arrange
    country_outline = box(0, 0, 1.5, 1)

    # Act
    spatial_extents = build_spatial_extents(
        station_codes=["UPSTREAM"],
        basin_chains={"UPSTREAM": [1, 2]},
        basins=create_river_basins(),
        country_outline=country_outline,
    )

    # Assert
    assert [spatial_extent.station_code for spatial_extent in spatial_extents] == [
        "UPSTREAM"
    ]
    assert spatial_extents[0].hydrobasins_ids == [1, 2]
    assert spatial_extents[0].geometry.bounds == (0.0, 0.0, 1.5, 1.0)


def test_station_whose_basins_lie_outside_the_country_is_left_out():
    # Arrange
    country_outline = box(10, 10, 11, 11)

    # Act
    spatial_extents = build_spatial_extents(
        station_codes=["UPSTREAM", "NOT_TRACED"],
        basin_chains={"UPSTREAM": [1, 2]},
        basins=create_river_basins(),
        country_outline=country_outline,
    )

    # Assert
    assert spatial_extents == []


def test_written_file_is_a_feature_collection_with_one_station_per_line(tmp_path):
    # Arrange
    output_path = tmp_path / "MWI_station_spatial_extents.geojson"
    spatial_extents = [
        StationSpatialExtent("G1", [1, 2], box(0, 0, 2, 1)),
        StationSpatialExtent("G2", [3], box(2, 0, 3, 1)),
    ]

    # Act
    write_spatial_extents(spatial_extents, output_path)

    # Assert
    text = output_path.read_text(encoding="utf-8")
    collection = json.loads(text)
    assert collection["type"] == "FeatureCollection"
    assert [
        feature["properties"]["station_code"] for feature in collection["features"]
    ] == ["G1", "G2"]
    assert collection["features"][0]["properties"]["hydrobasins_ids"] == [1, 2]
    assert collection["features"][0]["geometry"]["type"] == "Polygon"
    assert len(text.splitlines()) == len(spatial_extents) + 2
