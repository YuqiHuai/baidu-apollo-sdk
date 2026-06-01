"""Tests for high-level cyber-bridge client behavior."""

from typing import Any

import pytest

from baidu_apollo_sdk.cyber_rt.channel import Topic
from baidu_apollo_sdk.cyber_rt.client import CyberClient


class FakeBridge:
    """Record bridge calls without opening a socket."""

    def __init__(self) -> None:
        self.container = object()
        self.calls: list[tuple[str, str, bytes | None]] = []

    def add_publisher(self, topic: Topic[Any]) -> None:
        """Record writer registration."""
        self.calls.append(("add_publisher", topic.channel, None))

    def publish(self, topic: Topic[Any], message: bytes) -> None:
        """Record one publication."""
        self.calls.append(("publish", topic.channel, message))


def test_publish_waits_after_registering_each_new_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = FakeBridge()
    sleeps: list[float] = []
    monkeypatch.setattr(
        "baidu_apollo_sdk.cyber_rt.client.time.sleep",
        sleeps.append,
    )
    client = CyberClient(
        bridge,  # type: ignore[arg-type]
        publisher_registration_delay=0.25,
    )
    topic_a = Topic("/a", "apollo.A", bytes)
    topic_b = Topic("/b", "apollo.B", bytes)

    client.publish(topic_a, b"first")
    client.publish(topic_a, b"second")
    client.publish(topic_b, b"third")

    assert bridge.calls == [
        ("add_publisher", "/a", None),
        ("publish", "/a", b"first"),
        ("publish", "/a", b"second"),
        ("add_publisher", "/b", None),
        ("publish", "/b", b"third"),
    ]
    assert sleeps == [0.25, 0.25]
