"""Version-independent command types."""

from dataclasses import dataclass
from typing import Any, Protocol

from google.protobuf.message import Message

from baidu_apollo_sdk.cyber_rt.channel import Topic


@dataclass(frozen=True)
class Pose:
    """Cartesian routing pose."""

    x: float
    y: float
    heading: float | None = None
    z: float | None = None


@dataclass(frozen=True)
class Header:
    """CyberRT message header metadata."""

    timestamp_sec: float
    module_name: str
    sequence_num: int


@dataclass(frozen=True)
class LaneFollowCommand:
    """Request lane-follow routing through optional intermediate waypoints."""

    start_pose: Pose
    end_pose: Pose
    waypoints: tuple[Pose, ...] = ()
    header: Header | None = None
    command_id: int | None = None
    target_speed: float | None = None


@dataclass(frozen=True)
class ParkingCommand:
    """Request routing from an initial pose into a parking space."""

    initial_pose: Pose
    parking_space_id: str
    header: Header | None = None
    task_header: Header | None = None


@dataclass(frozen=True)
class Publication:
    """One serialized-message publication produced for a command."""

    topic: Topic[Message]
    message: Message


class CommandEncoder(Protocol):
    """Compile semantic commands for one Apollo version."""

    def encode_lane_follow(
        self, command: LaneFollowCommand
    ) -> tuple[Publication, ...]:
        """Compile a lane-follow command."""
        ...

    def encode_parking(
        self, command: ParkingCommand, map_service: Any
    ) -> tuple[Publication, ...]:
        """Compile a parking command using loaded HD-map metadata."""
        ...
