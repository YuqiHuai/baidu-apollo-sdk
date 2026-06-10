"""Apollo v7 command encoder."""

from typing import Any

from baidu_apollo_proto.v7.modules.planning.proto import pad_msg_pb2
from baidu_apollo_proto.v7.modules.routing.proto.routing_pb2 import (
    RoutingRequest,
)
from baidu_apollo_proto.v7.modules.task_manager.proto import task_manager_pb2
from google.protobuf.message import Message

from baidu_apollo_sdk.cyber_rt.channel import Topic
from baidu_apollo_sdk.cyber_rt.decoder import decode_proto

from .base import (
    ACTION_COMMANDS_V7,
    ActionCommand,
    LaneFollowCommand,
    ParkingCommand,
    Publication,
    validate_action_command,
)
from .routing import (
    _set_header,
    encode_parking_request,
    encode_routing_request,
)

TASK_MANAGER_CHANNEL = "/apollo/task_manager"
PLANNING_PAD_CHANNEL = "/apollo/planning/pad"
_ACTION_VALUES_V7 = {
    "FOLLOW": pad_msg_pb2.FOLLOW,
    "CHANGE_LEFT": pad_msg_pb2.CHANGE_LEFT,
    "CHANGE_RIGHT": pad_msg_pb2.CHANGE_RIGHT,
    "PULL_OVER": pad_msg_pb2.PULL_OVER,
    "STOP": pad_msg_pb2.STOP,
    "RESUME_CRUISE": pad_msg_pb2.RESUME_CRUISE,
}


def _task_manager_topic() -> Topic[Message]:
    """Build v7 task-manager topic metadata."""
    message_type = task_manager_pb2.Task
    return Topic(
        TASK_MANAGER_CHANNEL,
        message_type.DESCRIPTOR.full_name,
        decode_proto(message_type),
        message_type.DESCRIPTOR.file,
    )


def _planning_pad_topic() -> Topic[Message]:
    """Build v7 planning pad topic metadata."""
    message_type = pad_msg_pb2.PadMessage
    return Topic(
        PLANNING_PAD_CHANNEL,
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

    def encode_action(self, command: ActionCommand) -> tuple[Publication, ...]:
        """Encode a v7 planning pad action command."""
        validate_action_command(command, ACTION_COMMANDS_V7, "Apollo v7")
        pad_message = pad_msg_pb2.PadMessage()
        pad_message.action = _ACTION_VALUES_V7[command.command]
        return (Publication(topic=_planning_pad_topic(), message=pad_message),)
