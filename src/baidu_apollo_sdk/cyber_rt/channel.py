"""Topic metadata types used by the CyberRT bridge client."""

from collections.abc import Callable
from dataclasses import dataclass

from google.protobuf.descriptor import FileDescriptor

type Decoder[T] = Callable[[bytes], T]
"""Callable that converts serialized CyberRT message bytes into an object."""


@dataclass(frozen=True)
class Topic[T]:
    """Describes a CyberRT topic and how to decode its messages.

    Attributes:
        channel: CyberRT channel name.
        msg_type: Fully qualified Apollo protobuf message type.
        decoder: Callable that decodes serialized message bytes.
        proto_descriptor: Optional protobuf file descriptor used when
            registering publishers with cyber-bridge.
    """

    channel: str
    msg_type: str
    decoder: Decoder[T]
    proto_descriptor: FileDescriptor | None = None


Channel = Topic
"""Backward-compatible alias for `Topic`."""
