from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pytest
from websocket import WebSocketConnectionClosedException

from baidu_apollo_sdk.dreamview import (
    Dreamview,
    DreamviewConnectionError,
    DreamviewModes,
    DreamviewOperations,
)
from baidu_apollo_sdk.dreamview.v7 import DreamviewV7
from baidu_apollo_sdk.dreamview.v11 import DreamviewV11


class FakeDreamviewContainer:
    version = 11

    @property
    def ip_address(self) -> str:
        return "172.17.0.2"

    @property
    def container_name(self) -> str:
        return "apollo_dev_test"


class FakeWebSocket:
    def __init__(
        self,
        *,
        send_error: Exception | None = None,
        recv_items: list[str | Exception | Callable[[], str]] | None = None,
    ) -> None:
        self.send_error = send_error
        self.recv_items = recv_items or []
        self.sent: list[dict[str, Any]] = []
        self.closed = False

    def send(self, data: str) -> int:
        if self.send_error is not None:
            exc = self.send_error
            self.send_error = None
            raise exc
        self.sent.append(json.loads(data))
        return len(data)

    def recv(self) -> str:
        item = self.recv_items.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item()
        return item

    def close(self) -> None:
        self.closed = True


class FakeDreamviewV7Container(FakeDreamviewContainer):
    version = 7


def test_dreamview_factory_selects_protocol_implementation() -> None:
    dreamview_v11 = Dreamview(FakeDreamviewContainer())
    dreamview_v7 = Dreamview(FakeDreamviewV7Container())

    assert isinstance(dreamview_v11, Dreamview)
    assert isinstance(dreamview_v11, DreamviewV11)
    assert isinstance(dreamview_v7, Dreamview)
    assert isinstance(dreamview_v7, DreamviewV7)


def test_dreamview_connect_wraps_connection_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def create_failing_connection(address: str) -> FakeWebSocket:
        assert address == "ws://172.17.0.2:8888/websocket"
        raise OSError("unreachable")

    monkeypatch.setattr(
        "baidu_apollo_sdk.dreamview.base.create_connection",
        create_failing_connection,
    )

    dreamview = Dreamview(FakeDreamviewContainer())

    with pytest.raises(DreamviewConnectionError, match="Failed to connect"):
        dreamview.connect()

    assert dreamview.socket_client is None


def test_dreamview_reconnects_and_retries_send(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_socket = FakeWebSocket(
        send_error=WebSocketConnectionClosedException("closed")
    )
    second_socket = FakeWebSocket()
    sockets = [first_socket, second_socket]

    def create_fake_connection(address: str) -> FakeWebSocket:
        assert address == "ws://172.17.0.2:8888/websocket"
        return sockets.pop(0)

    monkeypatch.setattr(
        "baidu_apollo_sdk.dreamview.base.create_connection",
        create_fake_connection,
    )

    dreamview = Dreamview(FakeDreamviewContainer())
    dreamview.connect()
    dreamview.set_mode(DreamviewModes.PNC)

    assert first_socket.closed is True
    assert second_socket.sent[0]["data"]["info"] == {
        "action": "CHANGE_MODE",
        "value": DreamviewModes.PNC,
    }
    assert dreamview.socket_client is second_socket


def test_dreamview_reconnects_and_replays_request_after_recv_loss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_socket = FakeWebSocket(
        recv_items=[WebSocketConnectionClosedException("closed")]
    )
    second_socket = FakeWebSocket()
    sockets = [first_socket, second_socket]

    def create_fake_connection(address: str) -> FakeWebSocket:
        assert address == "ws://172.17.0.2:8888/websocket"
        return sockets.pop(0)

    def recv_success_response() -> str:
        request_id = second_socket.sent[0]["data"]["requestId"]
        return json.dumps(
            {
                "action": "response",
                "data": {
                    "requestId": request_id,
                    "info": {"data": {"isOk": True}},
                },
            }
        )

    second_socket.recv_items.append(recv_success_response)
    monkeypatch.setattr(
        "baidu_apollo_sdk.dreamview.base.create_connection",
        create_fake_connection,
    )

    dreamview = Dreamview(FakeDreamviewContainer())
    dreamview.connect()

    assert dreamview.set_operation(DreamviewOperations.SIM_CONTROL) is True
    assert first_socket.closed is True
    assert first_socket.sent[0]["data"]["info"]["action"] == "CHANGE_OPERATION"
    assert second_socket.sent[0]["data"]["info"] == {
        "action": "CHANGE_OPERATION",
        "value": DreamviewOperations.SIM_CONTROL,
    }


def test_dreamview_can_disable_auto_reconnect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    socket = FakeWebSocket(
        send_error=WebSocketConnectionClosedException("closed")
    )

    def create_fake_connection(address: str) -> FakeWebSocket:
        assert address == "ws://172.17.0.2:8888/websocket"
        return socket

    monkeypatch.setattr(
        "baidu_apollo_sdk.dreamview.base.create_connection",
        create_fake_connection,
    )

    dreamview = Dreamview(FakeDreamviewContainer(), auto_reconnect=False)
    dreamview.connect()

    with pytest.raises(DreamviewConnectionError, match="connection lost"):
        dreamview.set_mode(DreamviewModes.PNC)

    assert socket.closed is True
    assert dreamview.socket_client is None


def test_dreamview_v7_sends_flat_hmi_action_payload() -> None:
    socket = FakeWebSocket()
    dreamview = Dreamview(FakeDreamviewV7Container())
    dreamview.socket_client = socket

    dreamview.set_mode(DreamviewModes.PNC)

    assert socket.sent == [
        {"type": "HMIAction", "action": "CHANGE_MODE", "value": "Pnc"}
    ]


def test_dreamview_v7_configures_sim_control_with_legacy_messages() -> None:
    socket = FakeWebSocket(
        recv_items=[json.dumps({"type": "VehicleParam", "length": 4.8})]
    )
    dreamview = Dreamview(FakeDreamviewV7Container())
    dreamview.socket_client = socket

    assert dreamview.set_up_for_sim_control() == {
        "type": "VehicleParam",
        "length": 4.8,
    }
    assert socket.sent == [
        {"type": "HMIAction", "action": "CHANGE_MODE", "value": "Pnc"},
        {"type": "ToggleSimControl", "enable": True},
        {
            "type": "HMIAction",
            "action": "CHANGE_VEHICLE",
            "value": "Mkz Example",
        },
    ]


def test_dreamview_v7_sends_start_point_in_routing_request() -> None:
    socket = FakeWebSocket(
        recv_items=[
            json.dumps({"type": "RoutingPointCheckResult"}),
            json.dumps({"type": "RoutingPointCheckResult"}),
            json.dumps({"type": "RoutingPointCheckResult"}),
        ]
    )
    dreamview = Dreamview(FakeDreamviewV7Container())
    dreamview.socket_client = socket

    assert dreamview.set_start_point(1.0, 2.0, 0.5) is True
    assert (
        dreamview.start_routing(
            [
                {"x": 3.0, "y": 4.0, "heading": 0.6},
                {"x": 5.0, "y": 6.0, "heading": 0.7},
            ]
        )
        is True
    )
    assert socket.sent[-1] == {
        "type": "SendRoutingRequest",
        "start": {"x": 1.0, "y": 2.0, "heading": 0.5},
        "waypoint": [{"x": 3.0, "y": 4.0, "heading": 0.6}],
        "end": {"x": 5.0, "y": 6.0, "heading": 0.7},
    }
