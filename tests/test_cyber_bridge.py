from __future__ import annotations

import socket

import pytest

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
