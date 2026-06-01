"""Apollo v11 command encoder."""

from typing import Any

from baidu_apollo_proto.v11.modules.common_msgs.routing_msgs import routing_pb2

from .base import LaneFollowCommand, ParkingCommand, Publication
from .routing import encode_parking_request


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
        """Encode a request for Apollo v11's old-routing adapter."""
        return (
            encode_parking_request(
                command,
                map_service,
                routing_pb2.RoutingRequest,
                set_start_pose_flag=True,
            ).publication,
        )
