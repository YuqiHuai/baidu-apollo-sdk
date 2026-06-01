"""Shared helpers for routing-request based command encoders."""

from dataclasses import dataclass
from typing import Any

from google.protobuf.message import Message

from baidu_apollo_sdk.cyber_rt.channel import Topic
from baidu_apollo_sdk.cyber_rt.decoder import decode_proto

from .base import Header, LaneFollowCommand, ParkingCommand, Pose, Publication

ROUTING_REQUEST_CHANNEL = "/apollo/routing_request"


@dataclass(frozen=True)
class EncodedParkingRequest:
    """Parking routing publication plus task-manager metadata."""

    publication: Publication
    lane_width: float


def routing_request_topic(message_type: type[Message]) -> Topic[Message]:
    """Build routing-request topic metadata for a protobuf schema."""
    return Topic(
        ROUTING_REQUEST_CHANNEL,
        message_type.DESCRIPTOR.full_name,
        decode_proto(message_type),
        message_type.DESCRIPTOR.file,
    )


def encode_routing_request(
    command: LaneFollowCommand,
    message_type: type[Message],
    *,
    set_start_pose_flag: bool,
) -> Publication:
    """Encode lane-follow poses as one routing-request publication."""
    request: Any = message_type()
    if set_start_pose_flag:
        request.is_start_pose_set = True
    _set_header(request, command.header)

    for pose in (command.start_pose, *command.waypoints, command.end_pose):
        _add_waypoint(request, pose)

    return Publication(
        topic=routing_request_topic(message_type),
        message=request,
    )


def encode_parking_request(
    command: ParkingCommand,
    map_service: Any,
    message_type: type[Message],
    *,
    set_start_pose_flag: bool,
) -> EncodedParkingRequest:
    """Encode parking routing metadata using one loaded HD map."""
    parking_space = map_service.get_parking_space_by_id(
        command.parking_space_id
    )
    extra_info = map_service.calc_parking_space_extra_info(parking_space)
    if extra_info is None:
        raise ValueError(
            "Cannot calculate routing metadata for parking space "
            f"{command.parking_space_id!r}"
        )

    request: Any = message_type()
    if set_start_pose_flag:
        request.is_start_pose_set = True
    _set_header(request, command.header)
    _add_waypoint(request, command.initial_pose)
    _add_waypoint(
        request,
        Pose(
            x=extra_info.routing_end_point.x,
            y=extra_info.routing_end_point.y,
        ),
    )

    parking_info = request.parking_info
    parking_info.parking_space_id = command.parking_space_id
    points = parking_space.polygon.point
    if not points:
        raise ValueError(
            f"Parking space {command.parking_space_id!r} has no polygon"
        )
    parking_info.parking_point.x = sum(point.x for point in points) / len(
        points
    )
    parking_info.parking_point.y = sum(point.y for point in points) / len(
        points
    )
    parking_info.parking_point.z = sum(point.z for point in points) / len(
        points
    )
    parking_info.parking_space_type = extra_info.parking_type
    for point in points:
        corner = parking_info.corner_point.point.add()
        corner.x = point.x
        corner.y = point.y
        corner.z = point.z

    return EncodedParkingRequest(
        publication=Publication(
            topic=routing_request_topic(message_type),
            message=request,
        ),
        lane_width=extra_info.lane_width,
    )


def _set_header(request: Any, header: Header | None) -> None:
    if header is None:
        return
    request.header.timestamp_sec = header.timestamp_sec
    request.header.module_name = header.module_name
    request.header.sequence_num = header.sequence_num


def _add_waypoint(
    request: Any, pose: Pose, *, lane_id: str | None = None
) -> None:
    waypoint = request.waypoint.add()
    if lane_id is not None:
        waypoint.id = lane_id
    waypoint.pose.x = pose.x
    waypoint.pose.y = pose.y
    if pose.z is not None:
        waypoint.pose.z = pose.z
    if pose.heading is not None:
        waypoint.heading = pose.heading
