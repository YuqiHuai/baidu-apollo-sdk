"""Apollo v11 command encoder."""

from typing import Any

from baidu_apollo_proto.v11.modules.common_msgs.external_command_msgs import (
    lane_follow_command_pb2,
)
from baidu_apollo_proto.v11.modules.common_msgs.routing_msgs import routing_pb2
from google.protobuf.message import Message

from baidu_apollo_sdk.cyber_rt.channel import Topic
from baidu_apollo_sdk.cyber_rt.decoder import decode_proto

from .base import LaneFollowCommand, ParkingCommand, Publication
from .routing import _set_header, encode_parking_request

EXTERNAL_COMMAND_LANE_FOLLOW_CHANNEL = "/apollo/external_command/lane_follow"


def _external_command_lane_follow_topic() -> Topic[Message]:
    """Build v11 external-command lane-follow topic metadata."""
    message_type = lane_follow_command_pb2.LaneFollowCommand
    return Topic(
        EXTERNAL_COMMAND_LANE_FOLLOW_CHANNEL,
        message_type.DESCRIPTOR.full_name,
        decode_proto(message_type),
        message_type.DESCRIPTOR.file,
    )


class CommandEncoderV11:
    """Compile semantic commands for Apollo v11."""

    def encode_lane_follow(
        self, command: LaneFollowCommand
    ) -> tuple[Publication, ...]:
        """Encode a request for Apollo v11's external-command topic."""
        request = lane_follow_command_pb2.LaneFollowCommand()
        _set_header(request, command.header)
        request.is_start_pose_set = True
        _add_way_point(request, command.start_pose)
        for pose in command.waypoints:
            _add_way_point(request, pose)
        _add_way_point(request, command.end_pose, end_pose=True)

        return (
            Publication(
                topic=_external_command_lane_follow_topic(),
                message=request,
            ),
        )

    def encode_parking(
        self, command: ParkingCommand, map_service: Any
    ) -> tuple[Publication, ...]:
        """Encode a request for Apollo v11's old-routing adapter."""
        return (
            encode_parking_request(
                command,
                map_service,
                routing_pb2.RoutingRequest,
                set_start_pose_flag=True,
            ).publication,
        )


def _add_way_point(
    request: Any, pose: Any, *, end_pose: bool = False
) -> None:
    """Append a pose to the external-command lane-follow message."""
    if end_pose:
        target = request.end_pose
    else:
        target = request.way_point.add()
    target.x = pose.x
    target.y = pose.y
    if pose.z is not None:
        target.z = pose.z
    if pose.heading is not None:
        target.heading = pose.heading
