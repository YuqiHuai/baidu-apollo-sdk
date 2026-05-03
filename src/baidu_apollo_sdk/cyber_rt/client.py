import queue
import threading
from collections import defaultdict
from collections.abc import Callable, Iterator
from typing import Any

from .bridge import CyberBridge
from .channel import Topic


class LatestValue:
    """Thread-safe container storing the most recent value."""

    def __init__(self) -> None:
        self._value: bytes | None = None
        self._lock = threading.Lock()
        self._event = threading.Event()

    def set(self, v: bytes) -> None:
        with self._lock:
            self._value = v
            self._event.set()

    def get(self, block: bool = False) -> bytes | None:
        if block:
            self._event.wait()
        with self._lock:
            return self._value


class CyberClient:
    """
    High-level CyberRT client.

    Responsibilities:
    - Manage publishers (deduplicated)
    - Manage subscriptions (fan-out)
    - Provide clean APIs (stream + latest)

    Internals:
    - ONE bridge subscription per channel
    - MANY local consumers
    """

    def __init__(self, bridge: CyberBridge) -> None:
        self.bridge = bridge

        # channel -> list of callbacks
        self._callbacks: dict[str, list[Callable[[bytes], None]]] = defaultdict(list)

        # channels subscribed at bridge level
        self._bridge_subscribed: set[str] = set()

        # channels with publishers registered
        self._publishers: set[str] = set()

    # -----------------------
    # Lifecycle
    # -----------------------

    def start(self) -> None:
        self.bridge.spin()

    def stop(self) -> None:
        self.bridge.stop()

    # -----------------------
    # Publish
    # -----------------------

    def publish(self, topic: Topic[Any], msg: bytes) -> None:
        ch = topic.channel

        if ch not in self._publishers:
            self.bridge.add_publisher(topic)
            self._publishers.add(ch)

        self.bridge.publish(topic, msg)

    # -----------------------
    # Subscription internals
    # -----------------------

    def _ensure_subscription(self, topic: Topic[Any]) -> None:
        """Ensure only one bridge-level subscription per channel."""

        ch = topic.channel

        if ch in self._bridge_subscribed:
            return

        def bridge_callback(msg: bytes) -> None:
            for cb in self._callbacks[ch]:
                cb(msg)

        self.bridge.add_subscriber(topic, bridge_callback)
        self._bridge_subscribed.add(ch)

    # -----------------------
    # Streaming subscription
    # -----------------------

    def subscribe(self, topic: Topic[Any]) -> Iterator[bytes]:
        """
        Stream messages from a channel.

        - Yields messages as they arrive
        - Drops old messages if consumer is slow
        """

        q: queue.Queue[bytes] = queue.Queue(maxsize=100)

        def callback(msg: bytes) -> None:
            if q.full():
                try:
                    q.get_nowait()  # drop oldest
                except queue.Empty:
                    pass
            q.put(msg)

        self._ensure_subscription(topic)
        self._callbacks[topic.channel].append(callback)

        while self.bridge.spinning:
            yield q.get()

    # -----------------------
    # Latest-value subscription
    # -----------------------

    def subscribe_latest(self, topic: Topic[Any]) -> LatestValue:
        """
        Subscribe to only the most recent value of a channel.

        Useful for high-frequency data (e.g. sensors).
        """

        latest = LatestValue()

        def callback(msg: bytes) -> None:
            latest.set(msg)

        self._ensure_subscription(topic)
        self._callbacks[topic.channel].append(callback)
        return latest
