"""Send semantic commands through a CyberRT bridge client."""

import time
from typing import Any, Protocol

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
        client: CommandPublisher,
        version: int = 11,
        *,
        map_service: object | None = None,
        publication_delay: float = 1.0,
    ) -> None:
        """Initialize a sender around a bridge client."""
        self.client = client
        self.version: ApolloVersion = claim_proto_version(version)
        self.encoder = create_command_encoder(self.version)
        self.map_service = map_service
        self.publication_delay = publication_delay

    def send_lane_follow(self, command: LaneFollowCommand) -> None:
        """Send a lane-follow command."""
        self._publish_all(self.encoder.encode_lane_follow(command))

    def send_parking(self, command: ParkingCommand) -> None:
        """Send a parking routing command."""
        if self.map_service is None:
            raise RuntimeError("Parking commands require a map service")
        self._publish_all(
            self.encoder.encode_parking(command, self.map_service)
        )

    def _publish_all(self, publications: tuple[Publication, ...]) -> None:
        for index, publication in enumerate(publications):
            if index:
                time.sleep(self.publication_delay)
            self.client.publish(
                publication.topic,
                publication.message.SerializeToString(),
            )
