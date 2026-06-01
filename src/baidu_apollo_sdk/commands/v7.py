"""Apollo v7 command encoder."""

from typing import Any

from baidu_apollo_proto.v7.modules.routing.proto.routing_pb2 import (
    RoutingRequest,
)
from baidu_apollo_proto.v7.modules.task_manager.proto import task_manager_pb2
from google.protobuf.message import Message

from baidu_apollo_sdk.cyber_rt.channel import Topic
from baidu_apollo_sdk.cyber_rt.decoder import decode_proto

from .base import LaneFollowCommand, ParkingCommand, Publication
from .routing import (
    _set_header,
    encode_parking_request,
    encode_routing_request,
)

TASK_MANAGER_CHANNEL = "/apollo/task_manager"


def _task_manager_topic() -> Topic[Message]:
    """Build v7 task-manager topic metadata."""
    message_type = task_manager_pb2.Task
    return Topic(
        TASK_MANAGER_CHANNEL,
        message_type.DESCRIPTOR.full_name,
        decode_proto(message_type),
        message_type.DESCRIPTOR.file,
    )


class CommandEncoderV7:
    """Compile semantic commands for Apollo v7."""

    def encode_lane_follow(
        self, command: LaneFollowCommand
    ) -> tuple[Publication, ...]:
        """Encode a legacy Apollo v7 routing request."""
        return (
            encode_routing_request(
                command,
                RoutingRequest,
                set_start_pose_flag=False,
            ),
        )

    def encode_parking(
        self, command: ParkingCommand, map_service: Any
    ) -> tuple[Publication, ...]:
        """Encode legacy v7 routing-request and task-manager publications."""
        encoded = encode_parking_request(
            command,
            map_service,
            RoutingRequest,
            set_start_pose_flag=False,
        )
        task = task_manager_pb2.Task()
        _set_header(task, command.task_header)
        task.task_name = "parking_routing_task"
        task.task_type = task_manager_pb2.PARKING_ROUTING
        task.parking_routing_task.lane_width = encoded.lane_width
        task.parking_routing_task.routing_request.CopyFrom(
            encoded.publication.message
        )
        task.parking_routing_task.routing_request.ClearField("header")

        return (
            encoded.publication,
            Publication(topic=_task_manager_topic(), message=task),
        )
