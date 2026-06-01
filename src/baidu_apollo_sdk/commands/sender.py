"""Send semantic commands through a CyberRT bridge client or HTTP service."""

import json
import time
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from baidu_apollo_sdk.cyber_rt.channel import Topic
from baidu_apollo_sdk.proto_version import claim_proto_version
from baidu_apollo_sdk.version import ApolloVersion

from .base import (
    CommandEncoder,
    LaneFollowCommand,
    ParkingCommand,
    Publication,
)


class CommandPublisher(Protocol):
    """Minimal CyberRT publication capability required by command sending."""

    def publish(self, topic: Topic[Any], msg: bytes) -> None:
        """Publish serialized bytes to a CyberRT topic."""
        ...


def create_command_encoder(version: int) -> CommandEncoder:
    """Create an encoder while loading only one Apollo protobuf schema."""
    apollo_version = claim_proto_version(version)
    if apollo_version == 7:
        from .v7 import CommandEncoderV7

        return CommandEncoderV7()

    from .v11 import CommandEncoderV11

    return CommandEncoderV11()


class CommandSender:
    """Compile and send semantic commands for one Apollo version."""

    def __init__(
        self,
        client: CommandPublisher | None,
        version: int = 11,
        *,
        map_service: object | None = None,
        publication_delay: float = 1.0,
        lane_follow_service_url: str | None = None,
    ) -> None:
        """Initialize a sender around a bridge client."""
        self.client = client
        self.version: ApolloVersion = claim_proto_version(version)
        self.encoder = create_command_encoder(self.version)
        self.map_service = map_service
        self.publication_delay = publication_delay
        self.lane_follow_service_url = lane_follow_service_url

    def send_lane_follow(self, command: LaneFollowCommand) -> Any:
        """Send a lane-follow command."""
        if self.version == 11:
            return self._send_v11_lane_follow(command)
        self._publish_all(self.encoder.encode_lane_follow(command))
        return None

    def send_parking(self, command: ParkingCommand) -> None:
        """Send a parking routing command."""
        if self.map_service is None:
            raise RuntimeError("Parking commands require a map service")
        self._publish_all(
            self.encoder.encode_parking(command, self.map_service)
        )

    def _publish_all(self, publications: tuple[Publication, ...]) -> None:
        client = self._require_client()
        for index, publication in enumerate(publications):
            if index:
                time.sleep(self.publication_delay)
            client.publish(
                publication.topic,
                publication.message.SerializeToString(),
            )

    def _require_client(self) -> CommandPublisher:
        if self.client is None:
            raise RuntimeError("This command requires a CyberRT publisher")
        return self.client

    def _send_v11_lane_follow(self, command: LaneFollowCommand) -> Any:
        if self.lane_follow_service_url is None:
            raise RuntimeError(
                "Apollo v11 lane-follow requires lane_follow_service_url"
            )

        payload: dict[str, Any] = {
            "isStartPoseSet": True,
            "wayPoint": [
                self._pose_payload(command.start_pose),
                *(
                    self._pose_payload(pose)
                    for pose in command.waypoints
                ),
            ],
            "endPose": self._pose_payload(command.end_pose),
        }
        if command.command_id is not None:
            payload["command_id"] = command.command_id
        if command.target_speed is not None:
            payload["target_speed"] = command.target_speed

        body = json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.lane_follow_service_url.rstrip('/')}/lane_follow",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request) as response:  # noqa: S310
                response_body = response.read()
        except HTTPError as exc:
            response_body = exc.read()
        if not response_body:
            return None
        return json.loads(response_body.decode("utf-8"))

    @staticmethod
    def _pose_payload(pose: Any) -> dict[str, float]:
        payload: dict[str, float] = {
            "x": pose.x,
            "y": pose.y,
        }
        if pose.z is not None:
            payload["z"] = pose.z
        if pose.heading is not None:
            payload["heading"] = pose.heading
        return payload
