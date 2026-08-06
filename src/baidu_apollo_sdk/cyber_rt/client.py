"""High-level client API for publishing and subscribing through cyber-bridge."""

import queue
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Iterator
from typing import Any

from baidu_apollo_sdk.logging import container_log_prefix, get_logger

from .bridge import CyberBridge
from .channel import Topic

logger = get_logger()


class LatestValue:
    """Thread-safe container storing the most recent value.

    The container is used by `CyberClient.subscribe_latest()` to expose the most
    recent raw message bytes for a topic without requiring callers to consume a
    blocking iterator.
    """

    def __init__(self) -> None:
        """Initialize an empty latest-value container."""
        self._value: bytes | None = None
        self._lock = threading.Lock()
        self._event = threading.Event()

    def set(self, v: bytes) -> None:
        """Store a new latest value and wake blocked readers.

        Args:
            v: Raw message bytes received from cyber-bridge.
        """
        with self._lock:
            self._value = v
            self._event.set()

    def get(self, block: bool = False) -> bytes | None:
        """Return the latest stored value.

        Args:
            block: If True, wait until at least one value has been stored.

        Returns:
            Latest raw message bytes, or None if no value has arrived and
            `block` is False.
        """
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

    def __init__(
        self,
        bridge: CyberBridge,
        *,
        publisher_registration_delay: float = 1.0,
    ) -> None:
        """Initialize a client around an active cyber-bridge connection.

        Args:
            bridge: Low-level bridge connection used for socket I/O.
            publisher_registration_delay: Seconds to wait after registering a
                new writer so existing CyberRT readers can discover it.
        """
        self.bridge = bridge
        self.publisher_registration_delay = publisher_registration_delay

        # channel -> list of callbacks
        self._callbacks: dict[str, list[Callable[[bytes], None]]] = defaultdict(
            list
        )

        # channels subscribed at bridge level
        self._bridge_subscribed: set[str] = set()

        # channels with publishers registered
        self._publishers: set[str] = set()

    # -----------------------
    # Lifecycle
    # -----------------------

    def start(self) -> None:
        """Start the bridge receive loop in the background."""
        logger.info(
            "{} client start", container_log_prefix(self.bridge.container)
        )
        self.bridge.spin()

    def stop(self) -> None:
        """Stop the bridge receive loop."""
        logger.info(
            "{} client stop", container_log_prefix(self.bridge.container)
        )
        self.bridge.stop()

    # -----------------------
    # Publish
    # -----------------------

    def publish(self, topic: Topic[Any], msg: bytes) -> None:
        """Publish serialized message bytes to a topic.

        Args:
            topic: Topic descriptor identifying the CyberRT channel and type.
            msg: Serialized protobuf payload.
        """
        ch = topic.channel

        if ch not in self._publishers:
            self.bridge.add_publisher(topic)
            self._publishers.add(ch)
            time.sleep(self.publisher_registration_delay)

        # Lazy: ``container_log_prefix`` reads ``container.ip_address``, a live
        # Docker API round-trip. This is a hot path -- the obstacle broker
        # publishes to every instance on every tick (25 Hz x N instances) --
        # and passing the prefix eagerly made each tick pay that cost per sink
        # even at INFO level, where the line is discarded. Every argument must
        # be a callable: loguru's lazy mode calls all of them.
        logger.opt(lazy=True).debug(
            "{} publish {}",
            lambda: container_log_prefix(self.bridge.container),
            lambda: ch,
        )
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
            """Fan out bridge messages to local subscribers."""
            for cb in self._callbacks[ch]:
                cb(msg)

        self.bridge.add_subscriber(topic, bridge_callback)
        self._bridge_subscribed.add(ch)
        logger.info(
            "{} client subscribe {}",
            container_log_prefix(self.bridge.container),
            ch,
        )

    # -----------------------
    # Streaming subscription
    # -----------------------

    def subscribe(self, topic: Topic[Any]) -> Iterator[bytes]:
        """Stream raw message bytes from a topic.

        The returned iterator blocks while waiting for messages. If the consumer
        is slow, old queued messages are dropped before new ones are enqueued.

        Args:
            topic: Topic descriptor to subscribe to.

        Yields:
            Raw serialized message bytes as they arrive.
        """

        q: queue.Queue[bytes] = queue.Queue(maxsize=100)

        def callback(msg: bytes) -> None:
            """Queue a streamed message, dropping the oldest item if needed."""
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
        """Subscribe to the latest raw value from a topic.

        This is useful for high-frequency topics where consumers only care about
        the newest message.

        Args:
            topic: Topic descriptor to subscribe to.

        Returns:
            Latest-value container updated by bridge callbacks.
        """

        latest = LatestValue()

        def callback(msg: bytes) -> None:
            """Store the newest message for latest-value subscribers."""
            latest.set(msg)

        self._ensure_subscription(topic)
        self._callbacks[topic.channel].append(callback)
        return latest
