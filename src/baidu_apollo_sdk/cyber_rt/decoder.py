"""Decoder helpers for CyberRT protobuf payloads."""

from collections.abc import Callable
from typing import cast

from google.protobuf.message import Message


def decode_proto[T: Message](cls: type[T]) -> Callable[[bytes], T]:
    """Build a decoder for a protobuf message class.

    Args:
        cls: Protobuf message class to instantiate and parse into.

    Returns:
        Callable that parses serialized protobuf bytes into `cls`.
    """

    def decoder(data: bytes) -> T:
        """Decode serialized protobuf bytes.

        Args:
            data: Serialized protobuf message.

        Returns:
            Parsed protobuf message instance.
        """
        msg = cls()
        msg.ParseFromString(data)
        return cast(T, msg)

    return decoder
