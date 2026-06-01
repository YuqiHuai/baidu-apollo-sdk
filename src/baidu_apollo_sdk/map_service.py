# /apollo/modules/map/hdmap/hdmap_impl.h
# /apollo/modules/map/hdmap/hdmap_impl.cc

from collections.abc import Iterable
from dataclasses import dataclass
from importlib import import_module
from math import atan2, pi
from pathlib import Path
from typing import Any, cast

import networkx as nx
from google.protobuf.message import Message
from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry

from baidu_apollo_sdk.kdtree import KDTree, KDTreeParams
from baidu_apollo_sdk.proto_version import claim_proto_version

DEFAULT_MAPS_DIR = Path(__file__).resolve().parents[2] / "assets" / "maps"
__loaded_instances: dict[tuple[Path, int], "MapService"] = {}


@dataclass
class SegmentInfo:
    lane_id: str
    segment_index: int


@dataclass
class PositionEstimate:
    lane_id: str
    s: float


@dataclass(frozen=True)
class ParkingSpaceExtraInfo:
    """Routing metadata calculated for one parking-space polygon."""

    order: tuple[int, int, int, int]
    parking_type: int
    lane_width: float
    routing_end_point: Point
    lane_id: str


def list_hd_maps(maps_dir: str | Path = DEFAULT_MAPS_DIR) -> list[str]:
    """List asset directories that contain an Apollo HD map binary."""
    root = Path(maps_dir)
    if not root.is_dir():
        return []
    return sorted(
        item.name
        for item in root.iterdir()
        if (item / "base_map.bin").is_file()
    )


def load_map_service(
    map_name: str,
    *,
    maps_dir: str | Path = DEFAULT_MAPS_DIR,
    version: int = 11,
    refresh: bool = False,
) -> "MapService":
    """Load an HD map from an asset directory and cache it in memory."""
    map_bin = (Path(maps_dir) / map_name / "base_map.bin").resolve()
    if not map_bin.is_file():
        raise FileNotFoundError(f"Requested map does not exist: {map_bin}")

    key = (map_bin, version)
    if refresh or key not in __loaded_instances:
        instance = MapService(version=version)
        instance.load_map_from_file(map_bin)
        __loaded_instances[key] = instance
    return __loaded_instances[key]


def _map_message_type(version: int) -> type[Message]:
    apollo_version = claim_proto_version(version)
    if apollo_version == 7:
        module_name = "baidu_apollo_proto.v7.modules.map.proto.map_pb2"
    else:
        module_name = (
            "baidu_apollo_proto.v11.modules.common_msgs.map_msgs.map_pb2"
        )

    return cast(type[Message], import_module(module_name).Map)


def is_allowed_to_cross(boundary: Any) -> bool:
    for boundary_type in boundary.boundary_type:
        # DOTTED_YELLOW = 1
        # DOTTED_WHITE = 2
        if not boundary_type.types or boundary_type.types[0] not in [1, 2]:
            return False
    return True


def _midpoint(first: Point, second: Point) -> Point:
    return Point((first.x + second.x) / 2, (first.y + second.y) / 2)


def _direction_vector_cross_product(
    first: tuple[float, float], second: tuple[float, float]
) -> float:
    return abs(first[0] * second[1] - first[1] * second[0])


def _point_on_vector_right(point: Point, start: Point, end: Point) -> bool:
    vector = (end.x - start.x, end.y - start.y)
    relative = (point.x - start.x, point.y - start.y)
    return bool(vector[0] * relative[1] - vector[1] * relative[0] < 0)


def _direction_same_with_vector(
    start: Point, end: Point, vector: tuple[float, float]
) -> bool:
    return bool(
        (end.x - start.x) * vector[0] + (end.y - start.y) * vector[1] > 0
    )


def _project_point_to_line(point: Point, start: Point, end: Point) -> Point:
    vector = (end.x - start.x, end.y - start.y)
    length_squared = vector[0] ** 2 + vector[1] ** 2
    if length_squared == 0:
        raise ValueError("Cannot project onto a zero-length line")
    scale = abs(
        (point.x - start.x) * vector[0]
        + (point.y - start.y) * vector[1]
    ) / length_squared
    return Point(start.x + scale * vector[0], start.y + scale * vector[1])


def _line_distance(point: Point, start: Point, end: Point) -> float:
    return float(point.distance(_project_point_to_line(point, start, end)))


def _get_point_distance_apart(
    points: list[Point],
    start: Point,
    distance: float,
    *,
    successor: bool,
    vector: tuple[float, float] | None = None,
) -> Point | None:
    indices = (
        range(len(points))
        if successor
        else range(len(points) - 1, -1, -1)
    )
    for index in indices:
        point = points[index]
        if vector is not None:
            relative = (
                point.x - start.x if successor else start.x - point.x,
                point.y - start.y if successor else start.y - point.y,
            )
            if relative[0] * vector[0] + relative[1] * vector[1] <= 0:
                continue
        if start.distance(point) >= distance:
            return point
    return None


class MapService:
    kSearchRadius = 3.0
    kMaxHeadingDiff = 1.0
    kParkingRoutingDistanceThreshold = 20.0

    FLAGS_min_length_for_lane_change = 1.0

    lane_kdtree: KDTree
    junction_kdtree: KDTree
    crosswalk_kdtree: KDTree
    signal_kdtree: KDTree
    stop_sign_kdtree: KDTree

    def __init__(self, version: int = 11) -> None:
        self.version = claim_proto_version(version)
        self.lane_table: dict[str, Any] = {}
        self.junction_table: dict[str, Any] = {}
        self.crosswalk_table: dict[str, Any] = {}
        self.signal_table: dict[str, Any] = {}
        self.stop_sign_table: dict[str, Any] = {}
        self.overlap_table: dict[str, Any] = {}
        self.parking_space_table: dict[str, Any] = {}

        self.lane_boxes: dict[BaseGeometry, SegmentInfo] = {}
        self.junction_boxes: dict[BaseGeometry, str] = {}
        self.crosswalk_boxes: dict[BaseGeometry, str] = {}
        self.signal_boxes: dict[BaseGeometry, str] = {}
        self.stop_sign_boxes: dict[BaseGeometry, str] = {}

        self.junction_lanes: list[str] = []
        self.non_junction_lanes: list[str] = []

        self.routing_graph = nx.DiGraph()
        self.obs_routing_graph = nx.DiGraph()

    def load_map_from_file(self, filename: str | Path) -> None:
        map_proto = _map_message_type(self.version)()
        map_proto.ParseFromString(Path(filename).read_bytes())
        self.load_map_from_proto(map_proto)

    def load_map_from_proto(self, map_proto: Any) -> None:
        obj_table_map = [
            (map_proto.lane, self.lane_table),
            (map_proto.junction, self.junction_table),
            (map_proto.crosswalk, self.crosswalk_table),
            (map_proto.signal, self.signal_table),
            (map_proto.stop_sign, self.stop_sign_table),
            (map_proto.overlap, self.overlap_table),
            (map_proto.parking_space, self.parking_space_table),
        ]
        for objects, table_name in obj_table_map:
            for obj in objects:
                table_name[obj.id.id] = obj

        self.build_lane_segment_kd_tree()
        self.build_routing_graph()
        self.find_non_junction_lanes()
        # self.build_junction_polygon_kd_tree()
        # self.build_signal_segment_kd_tree()
        # self.build_crosswalk_polygon_kd_tree()
        # self.build_stop_sign_segment_kd_tree()

    def get_lanes(
        self, point: Point | None = None, distance: float = 0.0
    ) -> Iterable[str]:
        if distance == 0.0:
            return self.lane_table.keys()
        if point is None:
            raise ValueError("point is required when distance is non-zero")
        return self.__get_lanes(point, distance)

    def __get_lanes(self, point: Point, distance: float) -> Iterable[str]:
        nearby_objects = self.lane_kdtree.get_objects(point, distance)
        result = set()
        for obj in nearby_objects:
            result.add(self.lane_boxes[obj].lane_id)
        return result

    def get_junctions(
        self, point: Point, distance: float = 0.0
    ) -> Iterable[str]:
        if distance == 0.0:
            return self.junction_table.keys()
        raise NotImplementedError()

    def get_crosswalks(
        self, point: Point, distance: float = 0.0
    ) -> Iterable[str]:
        if distance == 0.0:
            return self.crosswalk_table.keys()
        raise NotImplementedError()

    def get_signals(self, point: Point, distance: float = 0.0) -> Iterable[str]:
        if distance == 0.0:
            return self.signal_table.keys()
        raise NotImplementedError()

    def get_stop_signs(
        self, point: Point, distance: float = 0.0
    ) -> Iterable[str]:
        if distance == 0.0:
            return self.stop_sign_table.keys()
        raise NotImplementedError()

    def get_lane_by_id(self, lane_id: str) -> Any:
        return self.lane_table[lane_id]

    def get_lane_central_curve_by_id(self, lane_id: str) -> LineString:
        lane_obj = self.get_lane_by_id(lane_id)
        cv = lane_obj.central_curve
        cv_points = cv.segment[0].line_segment
        return LineString([[x.x, x.y] for x in cv_points.point])

    def get_lane_boundary_types_by_id(self, lane_id: str) -> tuple[int, int]:
        lane_obj = self.get_lane_by_id(lane_id)
        return (
            lane_obj.left_boundary.boundary_type[0].types[0],
            lane_obj.right_boundary.boundary_type[0].types[0],
        )

    def get_lane_boundaries_by_id(
        self, lane_id: str
    ) -> tuple[LineString, LineString]:
        lane_obj = self.get_lane_by_id(lane_id)

        left_boundary_points: list[tuple[float, float]] = []
        right_boundary_points: list[tuple[float, float]] = []

        for result_container, boundary_obj in [
            (left_boundary_points, lane_obj.left_boundary),
            (right_boundary_points, lane_obj.right_boundary),
        ]:
            for segment in boundary_obj.curve.segment:
                for segment_point in segment.line_segment.point:
                    result_container.append((segment_point.x, segment_point.y))
        return LineString(left_boundary_points), LineString(
            right_boundary_points
        )

    def get_junction_by_id(self, junction_id: str) -> Any:
        return self.junction_table[junction_id]

    def get_crosswalk_by_id(self, crosswalk_id: str) -> Any:
        return self.crosswalk_table[crosswalk_id]

    def get_signal_by_id(self, signal_id: str) -> Any:
        return self.signal_table[signal_id]

    def get_stop_sign_by_id(self, stop_sign_id: str) -> Any:
        return self.stop_sign_table[stop_sign_id]

    def get_overlap_by_id(self, overlap_id: str) -> Any:
        return self.overlap_table[overlap_id]

    def get_parking_space_by_id(self, parking_space_id: str) -> Any:
        return self.parking_space_table[parking_space_id]

    def calc_parking_space_extra_info(
        self,
        parking_space: Any,
        routing_distance_threshold: float = kParkingRoutingDistanceThreshold,
    ) -> ParkingSpaceExtraInfo | None:
        """Calculate parking-space corner order and a nearby routing endpoint.

        This ports Dreamview's ``calcParkingSpaceExtraInfo`` calculation. The
        parking space must overlap a loaded lane and its polygon must contain
        four points.
        """
        border = [
            Point(point.x, point.y) for point in parking_space.polygon.point
        ]
        if len(border) != 4:
            return None

        lane_id = self._get_parking_space_lane_id(parking_space)
        if lane_id is None:
            return None

        center_line = self._get_lane_center_line(lane_id)
        lane_start = Point(center_line.coords[0])
        lane_end = Point(center_line.coords[-1])
        lane_vector = (
            lane_end.x - lane_start.x,
            lane_end.y - lane_start.y,
        )
        if lane_vector == (0.0, 0.0):
            return None

        order = self._get_parking_space_order(border, lane_start, lane_end)
        successor = _direction_same_with_vector(
            border[order[0]], border[order[1]], lane_vector
        )
        projection = _project_point_to_line(
            border[order[2]], lane_start, lane_end
        )
        lane_width = border[order[2]].distance(projection) * 4
        routing_result = self._get_routing_point(
            lane_id,
            projection,
            successor,
            routing_distance_threshold,
        )
        if routing_result is None:
            return None

        routing_end_point, routing_lane_id = routing_result
        parking_type = int(
            border[order[0]].distance(border[order[1]])
            >= border[order[2]].distance(border[order[1]])
        )
        return ParkingSpaceExtraInfo(
            order=order,
            parking_type=parking_type,
            lane_width=lane_width,
            routing_end_point=routing_end_point,
            lane_id=routing_lane_id,
        )

    def calcParkingSpaceExtraInfo(  # noqa: N802
        self,
        parking_space: Any,
        routing_distance_threshold: float = kParkingRoutingDistanceThreshold,
    ) -> ParkingSpaceExtraInfo | None:
        """Compatibility alias matching the Dreamview method name."""
        return self.calc_parking_space_extra_info(
            parking_space, routing_distance_threshold
        )

    def _get_parking_space_lane_id(self, parking_space: Any) -> str | None:
        if not parking_space.overlap_id:
            return None
        overlap_id = parking_space.overlap_id[0].id
        for lane_id, lane in self.lane_table.items():
            if any(item.id == overlap_id for item in lane.overlap_id):
                return lane_id
        return None

    def _get_lane_center_line(self, lane_id: str) -> LineString:
        points: list[tuple[float, float]] = []
        for segment in self.get_lane_by_id(lane_id).central_curve.segment:
            for point in segment.line_segment.point:
                coordinate = (point.x, point.y)
                if not points or points[-1] != coordinate:
                    points.append(coordinate)
        if len(points) < 2:
            raise ValueError(f"Lane {lane_id!r} has no usable central curve")
        return LineString(points)

    def _get_parking_space_order(
        self, border: list[Point], lane_start: Point, lane_end: Point
    ) -> tuple[int, int, int, int]:
        lane_vector = (lane_end.x - lane_start.x, lane_end.y - lane_start.y)
        vector_01 = (border[1].x - border[0].x, border[1].y - border[0].y)
        vector_12 = (border[1].x - border[2].x, border[1].y - border[2].y)
        parallel = (
            2
            if _direction_vector_cross_product(lane_vector, vector_01)
            > _direction_vector_cross_product(lane_vector, vector_12)
            else 1
        )

        if parallel == 1:
            mid_01 = _midpoint(border[0], border[1])
            mid_23 = _midpoint(border[2], border[3])
            intersection = _project_point_to_line(mid_01, lane_start, lane_end)
            compare_y = (
                intersection.x == mid_01.x
                or intersection.x == mid_23.x
                or mid_01.x == mid_23.x
            )
            intersection_before = (
                intersection.y < mid_01.y
                if compare_y
                else intersection.x < mid_01.x
            )
            mid_01_before = (
                mid_01.y < mid_23.y if compare_y else mid_01.x < mid_23.x
            )
            if intersection_before == mid_01_before:
                return (
                    (3, 2, 1, 0)
                    if _point_on_vector_right(border[3], mid_01, mid_23)
                    else (2, 3, 0, 1)
                )
            return (
                (0, 1, 2, 3)
                if _point_on_vector_right(border[0], mid_23, mid_01)
                else (1, 0, 3, 2)
            )

        mid_12 = _midpoint(border[1], border[2])
        mid_03 = _midpoint(border[0], border[3])
        intersection = _project_point_to_line(mid_12, lane_start, lane_end)
        compare_y = (
            intersection.x == mid_12.x
            or intersection.x == mid_03.x
            or mid_12.x == mid_03.x
        )
        intersection_before = (
            intersection.y < mid_12.y
            if compare_y
            else intersection.x < mid_12.x
        )
        mid_12_before = (
            mid_12.y < mid_03.y if compare_y else mid_12.x < mid_03.x
        )
        if intersection_before == mid_12_before:
            return (
                (0, 3, 2, 1)
                if _point_on_vector_right(border[0], mid_12, mid_03)
                else (3, 0, 1, 2)
            )
        return (
            (1, 2, 3, 0)
            if _point_on_vector_right(border[1], mid_03, mid_12)
            else (2, 1, 0, 3)
        )

    def _get_routing_point(
        self,
        lane_id: str,
        start_point: Point,
        successor: bool,
        distance: float,
    ) -> tuple[Point, str] | None:
        if distance < 0:
            raise ValueError("routing distance threshold must be non-negative")

        lane = self.get_lane_by_id(lane_id)
        points = self._get_lane_center_points(lane)
        target_point = points[-1] if successor else points[0]
        traveled = start_point.distance(target_point)
        if traveled >= distance:
            lane_vector = (
                points[-1].x - points[0].x,
                points[-1].y - points[0].y,
            )
            routing_point = _get_point_distance_apart(
                points,
                start_point,
                distance,
                successor=successor,
                vector=lane_vector,
            )
            if routing_point is None:
                return None
            return routing_point, lane_id

        next_ids = lane.successor_id if successor else lane.predecessor_id
        visited = {lane_id}
        while traveled < distance and next_ids:
            next_lane_id = next_ids[0].id
            if next_lane_id in visited or next_lane_id not in self.lane_table:
                return None
            visited.add(next_lane_id)
            lane = self.get_lane_by_id(next_lane_id)
            remaining = distance - traveled
            lane_length = float(lane.length)
            if lane_length >= remaining:
                routing_point = self._get_point_on_lane(
                    lane, remaining, successor=successor
                )
                if routing_point is None:
                    return None
                return routing_point, next_lane_id
            traveled += lane_length
            next_ids = lane.successor_id if successor else lane.predecessor_id
        return None

    def _get_lane_center_points(self, lane: Any) -> list[Point]:
        points: list[Point] = []
        for segment in lane.central_curve.segment:
            for point in segment.line_segment.point:
                coordinate = Point(point.x, point.y)
                if not points or points[-1] != coordinate:
                    points.append(coordinate)
        return points

    def _get_point_on_lane(
        self, lane: Any, distance: float, *, successor: bool
    ) -> Point | None:
        segments = lane.central_curve.segment
        indices = (
            range(len(segments))
            if successor
            else range(len(segments) - 1, -1, -1)
        )
        remaining = distance
        for index in indices:
            segment = segments[index]
            segment_length = float(segment.length)
            if remaining > segment_length:
                remaining -= segment_length
                continue
            points = [
                Point(point.x, point.y) for point in segment.line_segment.point
            ]
            return _get_point_distance_apart(
                points,
                points[0] if successor else points[-1],
                remaining,
                successor=successor,
            )
        return None

    def get_path_from(
        self, lane_id: str, forward_only: bool = True, limit: int = 15
    ) -> list[list[str]]:
        result: list[list[str]] = []
        if limit == 0:
            return result
        for _, target in self.routing_graph.edges(lane_id):
            edge_data = self.routing_graph.get_edge_data(lane_id, target)
            if forward_only and edge_data["direction_type"] in ["L", "R"]:
                continue
            result.append([lane_id, target])
            for path in self.get_path_from(target, forward_only, limit - 1):
                result.append([lane_id] + path)
        return result

    def find_non_junction_lanes(self) -> None:
        self.junction_lanes = list()
        self.non_junction_lanes = list()
        junction_overlap_ids = set()
        # find all overlap ids that are associated with junctions
        for junction in self.junction_table:
            junction_obj = self.junction_table[junction]
            for oid in junction_obj.overlap_id:
                junction_overlap_ids.add(oid.id)
        # find all lanes that are not associated with junctions
        for lane_id in self.lane_table:
            lane_obj = self.lane_table[lane_id]
            lane_overlap_ids = {x.id for x in lane_obj.overlap_id}
            if not lane_overlap_ids & junction_overlap_ids:
                self.non_junction_lanes.append(lane_id)
            else:
                self.junction_lanes.append(lane_id)

    def build_routing_graph(self) -> None:
        # modules/routing/topo_creator/graph_creator.cc
        for lane_id in self.lane_table:
            pred = [x.id for x in self.lane_table[lane_id].predecessor_id]
            succ = [x.id for x in self.lane_table[lane_id].successor_id]
            l_neighbor = [
                x.id
                for x in self.lane_table[lane_id].left_neighbor_forward_lane_id
            ]
            r_neighbor = [
                x.id
                for x in self.lane_table[lane_id].right_neighbor_forward_lane_id
            ]
            for pid in pred:
                self.routing_graph.add_edge(pid, lane_id, direction_type="F")
                self.obs_routing_graph.add_edge(pid, lane_id)
            for pid in succ:
                self.routing_graph.add_edge(lane_id, pid, direction_type="F")
                self.obs_routing_graph.add_edge(lane_id, pid)

            if (
                self.lane_table[lane_id].length
                < MapService.FLAGS_min_length_for_lane_change
            ):
                continue

            for pid in l_neighbor:
                if is_allowed_to_cross(self.lane_table[pid].left_boundary):
                    self.routing_graph.add_edge(
                        lane_id, pid, direction_type="L"
                    )
            for pid in r_neighbor:
                if is_allowed_to_cross(self.lane_table[pid].right_boundary):
                    self.routing_graph.add_edge(
                        lane_id, pid, direction_type="R"
                    )

    def build_lane_segment_kd_tree(self) -> None:
        params = KDTreeParams(max_leaf_dimension=5.0, max_leaf_size=16)
        objects: set[BaseGeometry] = set()
        for lane_id in self.lane_table:
            lane_obj = self.lane_table[lane_id]
            cv = lane_obj.central_curve
            cv_points = cv.segment[0].line_segment
            lst = LineString([[x.x, x.y] for x in cv_points.point])
            segments = [
                LineString(coordinates)
                for coordinates in zip(
                    lst.coords[:-1], lst.coords[1:], strict=True
                )
            ]
            for index, segment in enumerate(segments):
                self.lane_boxes[segment] = SegmentInfo(lane_id, index)
                objects.add(segment)
        self.lane_kdtree = KDTree(list(objects), params)

    def build_junction_polygon_kd_tree(self) -> None:
        # params = KDTreeParams(max_leaf_dimension=5.0, max_leaf_size=1)
        raise NotImplementedError()

    def build_crosswalk_polygon_kd_tree(self) -> None:
        # params = KDTreeParams(max_leaf_dimension=5.0, max_leaf_size=1)
        raise NotImplementedError()

    def build_signal_segment_kd_tree(self) -> None:
        # params = KDTreeParams(max_leaf_dimension=5.0, max_leaf_size=4)
        raise NotImplementedError()

    def build_stop_sign_segment_kd_tree(self) -> None:
        # params = KDTreeParams(max_leaf_dimension=5.0, max_leaf_size=4)
        raise NotImplementedError()

    def get_lane_coord_and_heading(
        self, lane_id: str, s: float
    ) -> tuple[Point, float]:
        return self.__get_lane_coord_and_heading(lane_id, s)

    def __get_lane_coord_and_heading(
        self, lane_id: str, s: float
    ) -> tuple[Point, float]:
        assert lane_id in self.lane_table.keys(), (
            f"lane_id {repr(lane_id)} does not exist"
        )
        assert self.get_lane_by_id(lane_id).length >= s

        cv = self.get_lane_by_id(lane_id).central_curve
        cv_points = cv.segment[0].line_segment

        lst = LineString([[x.x, x.y] for x in cv_points.point])
        ip = lst.interpolate(s)

        segments = [
            LineString(coordinates)
            for coordinates in zip(lst.coords[:-1], lst.coords[1:], strict=True)
        ]
        segments.sort(key=lambda x: ip.distance(x))
        line = segments[0]
        x1, x2 = line.xy[0]
        y1, y2 = line.xy[1]

        return Point(ip.x, ip.y), atan2(y2 - y1, x2 - x1)

    def get_pose_with_regard_to_lane(self, point: Point) -> float:
        return self.__get_pose_with_regard_to_lane(point)

    def __get_pose_with_regard_to_lane(self, point: Point) -> float:
        obj = self.lane_kdtree.get_nearest_object(point)
        x1, x2 = obj.xy[0]
        y1, y2 = obj.xy[1]
        return atan2(y2 - y1, x2 - x1)

    def get_nearest_lane(self, point: Point) -> str:
        return self.__get_nearest_lane(point)

    def __get_nearest_lane(self, point: Point) -> str:
        obj = self.lane_kdtree.get_nearest_object(point)
        return self.lane_boxes[obj].lane_id

    def get_nearest_lanes_with_heading(
        self, point: Point, heading: float
    ) -> list[str]:
        return self.__get_nearest_lanes_with_heading(point, heading)

    def __get_nearest_lanes_with_heading(
        self, point: Point, heading: float
    ) -> list[str]:
        objs = list(self.lane_kdtree.get_objects(point, 3))
        if len(objs) == 0:
            return []

        filtered_objs = list()
        for i in range(len(objs)):
            x1, x2 = objs[i].xy[0]
            y1, y2 = objs[i].xy[1]
            theta = atan2(y2 - y1, x2 - x1)
            theta_diff = abs(heading - theta)
            unsigned_diff = min(theta_diff, 2 * pi - theta_diff)
            if unsigned_diff < self.kMaxHeadingDiff:
                filtered_objs.append((objs[i], theta, unsigned_diff))

        if len(filtered_objs) == 0:
            return list()

        filtered_objs.sort(key=lambda x: (x[0].distance(point), x[2]))
        result = list()
        for obj in filtered_objs:
            if self.lane_boxes[obj[0]].lane_id not in result:
                result.append(self.lane_boxes[obj[0]].lane_id)
        return result

    def get_predecessors_for_lane(self, lane_id: str) -> list[str]:
        return [x.id for x in self.lane_table[lane_id].predecessor_id]

    def get_successors_for_lane(self, lane_id: str) -> list[str]:
        return [x.id for x in self.lane_table[lane_id].successor_id]

    def get_length_of_lane(self, lane_id: str) -> float:
        return float(self.lane_table[lane_id].length)
