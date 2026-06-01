"""Apollo v11 command encoder."""

from typing import Any

from .base import ActionCommand, LaneFollowCommand, ParkingCommand, Publication


class CommandEncoderV11:
    """Compile semantic commands for Apollo v11."""

    def encode_lane_follow(
        self, command: LaneFollowCommand
    ) -> tuple[Publication, ...]:
        """Apollo v11 lane-follow is sent through the HTTP bridge."""
        raise RuntimeError(
            "Apollo v11 lane-follow is sent through the HTTP bridge"
        )

    def encode_parking(
        self, command: ParkingCommand, map_service: Any
    ) -> tuple[Publication, ...]:
        """Apollo v11 parking commands are sent through the HTTP bridge."""
        raise RuntimeError(
            "Apollo v11 parking is sent through the HTTP bridge"
        )

    def encode_action(self, command: ActionCommand) -> tuple[Publication, ...]:
        """Apollo v11 action commands are sent through the HTTP bridge."""
        raise RuntimeError("Apollo v11 action is sent through the HTTP bridge")
