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

    def connect(self, address: tuple[str, int]) -> None:
        self.connected_to = address

    def setblocking(self, flag: bool) -> None:
        self.blocking = flag


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
