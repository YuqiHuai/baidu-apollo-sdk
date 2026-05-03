from collections.abc import Callable
from dataclasses import dataclass

type Decoder[T] = Callable[[bytes], T]


@dataclass(frozen=True)
class Channel[T]:
    channel: str
    msg_type: str
    decoder: Decoder[T]
