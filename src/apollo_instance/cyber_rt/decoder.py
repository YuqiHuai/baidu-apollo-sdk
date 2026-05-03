from collections.abc import Callable
from typing import cast

from google.protobuf.message import Message


def decode_proto[T: Message](cls: type[T]) -> Callable[[bytes], T]:
    def decoder(data: bytes) -> T:
        msg = cls()
        msg.ParseFromString(data)
        return cast(T, msg)

    return decoder
