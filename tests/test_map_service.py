"""Tests for HD-map asset loading and geometry lookup."""

import subprocess
import sys
from math import hypot
from pathlib import Path
from types import SimpleNamespace

import pytest
from baidu_apollo_proto.v11.modules.common_msgs.map_msgs.map_pb2 import Map
from shapely.geometry import LineString, Point

from baidu_apollo_sdk import MapService, list_hd_maps, load_map_service
from baidu_apollo_sdk.kdtree import KDTree, KDTreeParams
from baidu_apollo_sdk.map_service import DEFAULT_MAPS_DIR


def _id(value: str) -> SimpleNamespace:
    return SimpleNamespace(id=value)


def _lane(
    lane_id: str,
    points: list[tuple[float, float]],
    *,
    overlaps: tuple[str, ...] = (),
    predecessors: tuple[str, ...] = (),
    successors: tuple[str, ...] = (),
) -> SimpleNamespace:
    line_points = [SimpleNamespace(x=x, y=y) for x, y in points]
    length = sum(
        hypot(end_x - start_x, end_y - start_y)
        for (start_x, start_y), (end_x, end_y) in zip(
            points[:-1], points[1:], strict=True
        )
    )
    segment = SimpleNamespace(
        line_segment=SimpleNamespace(point=line_points), length=length
    )
    return SimpleNamespace(
        id=_id(lane_id),
        central_curve=SimpleNamespace(segment=[segment]),
        length=length,
        overlap_id=[_id(item) for item in overlaps],
        successor_id=[_id(item) for item in successors],
        predecessor_id=[_id(item) for item in predecessors],
    )


def test_list_hd_maps_finds_asset_directories() -> None:
    assert "borregas_ave" in list_hd_maps()


def test_load_map_service_from_assets() -> None:
    service = load_map_service("borregas_ave", refresh=True)
    lane_id = next(iter(service.lane_table))
    lane_curve = service.get_lane_central_curve_by_id(lane_id)
    point = Point(lane_curve.coords[0])

    assert service.version == 11
    assert len(service.lane_table) == 60
    assert service.get_nearest_lane(point) in service.lane_table
    assert service.get_lanes(point, 3.0)
    assert load_map_service("borregas_ave") is service


def test_load_map_service_v7_in_fresh_process() -> None:
    script = """
from baidu_apollo_sdk.map_service import load_map_service
service = load_map_service("borregas_ave", version=7)
print(service.version, len(service.lane_table))
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "7 60"


def test_load_map_service_rejects_missing_map() -> None:
    with pytest.raises(FileNotFoundError, match="Requested map does not exist"):
        load_map_service("missing")


def test_load_map_from_proto_indexes_yield_signs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    map_proto = Map()
    yield_sign = getattr(map_proto, "yield").add()
    yield_sign.id.id = "yield-sign-1"
    service = MapService()
    monkeypatch.setattr(service, "build_lane_segment_kd_tree", lambda: None)

    service.load_map_from_proto(map_proto)

    assert list(service.get_yield_signs(Point())) == ["yield-sign-1"]
    assert service.get_yield_sign_by_id("yield-sign-1") == yield_sign


def test_kdtree_queries_nearest_geometry() -> None:
    near = LineString([(0, 0), (1, 0)])
    far = LineString([(10, 0), (11, 0)])
    tree = KDTree([near, far], KDTreeParams(max_leaf_size=1))

    assert tree.get_nearest_object(Point(0.5, 0.1)) == near
    assert tree.get_objects(Point(0.5, 0.1), 0.2) == [near]


def test_calc_parking_space_extra_info_routes_along_connected_lane() -> None:
    service = MapService()
    service.lane_table = {
        "lane-1": _lane(
            "lane-1",
            [(0, 0), (10, 0)],
            overlaps=("parking-overlap",),
            predecessors=("lane-2",),
        ),
        "lane-2": _lane("lane-2", [(-10, 0), (0, 0)]),
    }
    parking_space = SimpleNamespace(
        polygon=SimpleNamespace(
            point=[
                SimpleNamespace(x=2, y=2),
                SimpleNamespace(x=6, y=2),
                SimpleNamespace(x=6, y=4),
                SimpleNamespace(x=2, y=4),
            ]
        ),
        overlap_id=[_id("parking-overlap")],
    )

    extra_info = service.calc_parking_space_extra_info(
        parking_space, routing_distance_threshold=10
    )

    assert extra_info is not None
    assert extra_info.order == (2, 3, 0, 1)
    assert extra_info.parking_type == 1
    assert extra_info.lane_width == pytest.approx(8)
    assert extra_info.lane_id == "lane-2"
    assert (extra_info.routing_end_point.x, extra_info.routing_end_point.y) == (
        pytest.approx(-10),
        pytest.approx(0),
    )


@pytest.mark.parametrize(
    ("map_name", "parking_space_id", "expected_x", "expected_y", "expected_id"),
    [
        (
            "sunnyvale_with_two_offices",
            "11544",
            587223.2271624649,
            4141416.1291361004,
            "11565dup1_1_-1",
        ),
        (
            "sunnyvale_with_two_offices",
            "11543",
            587220.1969863597,
            4141415.605918677,
            "11565dup1_1_-1",
        ),
        (
            "san_mateo",
            "3111",
            559897.1631688222,
            4157624.968871962,
            "2361dup1_1_-1"
        )
    ],
)
def test_calc_parking_space_extra_info_from_sim_map(
    map_name: str,
    parking_space_id: str,
    expected_x: float,
    expected_y: float,
    expected_id: str,
) -> None:
    map_proto = Map()
    map_proto.ParseFromString(
        (Path(DEFAULT_MAPS_DIR) / map_name / "sim_map.bin").read_bytes()
    )
    service = MapService()
    service.lane_table = {lane.id.id: lane for lane in map_proto.lane}
    parking_spaces = {
        parking_space.id.id: parking_space
        for parking_space in map_proto.parking_space
    }

    extra_info = service.calc_parking_space_extra_info(
        parking_spaces[parking_space_id]
    )

    assert extra_info is not None
    assert extra_info.routing_end_point.x == pytest.approx(expected_x)
    assert extra_info.routing_end_point.y == pytest.approx(expected_y)
    assert extra_info.lane_id == expected_id
