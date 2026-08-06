from __future__ import annotations

import socket
import sys

import pytest
from loguru import logger

from baidu_apollo_sdk.cyber_rt.bridge import CyberBridge


class FakeBridgeContainer:
    @property
    def ip_address(self) -> str:
        return "172.17.0.2"

    @property
    def container_name(self) -> str:
        return "apollo_dev_test"


class FakeSocket:
    def __init__(self) -> None:
        self.connected_to: tuple[str, int] | None = None
        self.blocking: bool | None = None
        self.closed = False

    def connect(self, address: tuple[str, int]) -> None:
        self.connected_to = address

    def setblocking(self, flag: bool) -> None:
        self.blocking = flag

    def close(self) -> None:
        self.closed = True


def test_cyber_bridge_connects_to_container_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_socket = FakeSocket()
    container = FakeBridgeContainer()

    def socket_factory(
        family: socket.AddressFamily,
        kind: socket.SocketKind,
    ) -> FakeSocket:
        assert family == socket.AF_INET
        assert kind == socket.SOCK_STREAM
        return fake_socket

    monkeypatch.setattr(
        "baidu_apollo_sdk.cyber_rt.bridge.socket.socket", socket_factory
    )

    bridge = CyberBridge(container, port=1234)

    assert bridge.container is container
    assert bridge.container.container_name == "apollo_dev_test"
    assert fake_socket.connected_to == ("172.17.0.2", 1234)
    assert fake_socket.blocking is False


class _IpCountingContainer:
    """Container whose ``ip_address`` records every read.

    Stands in for the real ``ApolloContainer.ip_address``, which is a
    property that makes a live round-trip to the Docker daemon rather than
    returning a cached string.
    """

    def __init__(self) -> None:
        self.ip_lookups = 0

    @property
    def ip_address(self) -> str:
        self.ip_lookups += 1
        return "172.17.0.2"

    @property
    def container_name(self) -> str:
        return "apollo_dev_test"


def _packet(topic: bytes, payload: bytes) -> bytes:
    """One bridge wire packet: op, topic (len-prefixed), payload (len-prefixed)."""
    return (
        bytes([4])
        + len(topic).to_bytes(4, "little")
        + topic
        + len(payload).to_bytes(4, "little")
        + payload
    )


def test_packet_processing_never_reaches_for_the_container_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Receiving packets must not touch the Docker API, once per packet.

    Regression test for a live incident. ``_process_buffer`` logs the packet
    at DEBUG with ``container_log_prefix(self.container)`` -- and that prefix
    reads ``container.ip_address``, a Docker daemon round-trip costing
    ~0.5-0.9 ms. Passed as an eager argument it ran for *every* packet even
    at INFO level, where the formatted line is then thrown away, throttling
    this receive loop below Apollo's ~100 Hz localization rate. The resulting
    kernel socket backlog was drained FIFO, so the obstacle broker
    republished ever-older poses at a perfectly steady 25 Hz: measured at
    1.8 MB pending and ~3.8 s of pose staleness (tens of metres of phantom
    position error between instances) before the logs were made lazy.
    """
    fake_socket = FakeSocket()
    container = _IpCountingContainer()
    monkeypatch.setattr(
        "baidu_apollo_sdk.cyber_rt.bridge.socket.socket",
        lambda family, kind: fake_socket,
    )
    bridge = CyberBridge(container, port=1234)
    bridge.on_read = lambda packet: None

    # Connecting legitimately logs (and so may read the IP once); the hot
    # path is what this test is about.
    container.ip_lookups = 0

    logger.remove()
    # INFO is what a real campaign runs at, and the whole point is that a
    # discarded DEBUG line must still cost nothing.
    sink_id = logger.add(sys.stderr, level="INFO")
    try:
        bridge._buffer = b"".join(
            _packet(b"/apollo/localization/pose", b"x" * 64) for _ in range(50)
        )
        bridge._process_buffer()
    finally:
        logger.remove(sink_id)

    assert bridge._buffer == b""
    assert container.ip_lookups == 0, (
        f"processing 50 packets made {container.ip_lookups} Docker API calls "
        "for log prefixes that INFO-level logging discards"
    )


def test_stop_closes_the_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    """A caller that rebuilds the whole stack (e.g. a full container reset
    between trials) must be able to release the old bridge's socket fd by
    calling stop() -- otherwise every rebuild leaks one fd forever, and
    enough of them eventually break select() for the whole process (see
    bugs/apollo-v7-simcontrol-planning-desync's fd-exhaustion finding)."""
    fake_socket = FakeSocket()
    container = FakeBridgeContainer()

    monkeypatch.setattr(
        "baidu_apollo_sdk.cyber_rt.bridge.socket.socket",
        lambda family, kind: fake_socket,
    )

    bridge = CyberBridge(container, port=1234)
    bridge.stop()

    assert fake_socket.closed is True
