from collections.abc import Callable
from dataclasses import dataclass

from google.protobuf.descriptor import FileDescriptor

type Decoder[T] = Callable[[bytes], T]


@dataclass(frozen=True)
class Topic[T]:
    channel: str
    msg_type: str
    decoder: Decoder[T]
    proto_descriptor: FileDescriptor | None = None


Channel = Topic
