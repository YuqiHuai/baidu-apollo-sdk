"""Shared WebSocket transport for Apollo Dreamview clients."""

import json
from abc import ABCMeta
from collections.abc import Callable
from typing import Any, cast

import nanoid
from websocket import (
    WebSocketConnectionClosedException,
    WebSocketException,
    create_connection,
)

from baidu_apollo_sdk.logging import container_log_prefix, get_logger
from baidu_apollo_sdk.version import ApolloVersion, validate_apollo_version

logger = get_logger()


class DreamviewConnectionError(RuntimeError):
    """Raised when the Dreamview WebSocket connection fails."""


class DreamviewModes:
    """Known Dreamview mode names."""

    PNC = "Pnc"
    DEFAULT = "Default"
    PERCEPTION = "Perception"
    VEHICLE_TEST = "Vehicle Test"


class DreamviewOperations:
    """Known Dreamview operation names."""

    SIM_CONTROL = "Sim_Control"
    RECORD = "Record"


class DreamviewVehicles:
    """Known Dreamview vehicle profile names."""

    KITTI_140 = "Kitti 140"
    MKZ_121 = "Mkz 121"
    MKZ_EXAMPLE = "Mkz Example"
    MKZ_LGSVL_321 = "Mkz Lgsvl 321"
    NUSCENES_165 = "Nuscenes 165"


class _DreamviewMeta(ABCMeta):
    """Construct the protocol implementation selected by the container."""

    def __call__(
        cls,
        ctn: Any,
        *,
        auto_reconnect: bool = True,
        reconnect_attempts: int = 1,
    ) -> Any:
        if cls is DreamviewBase:
            # Lazy imports avoid a cycle between the shared base and protocols.
            # pylint: disable=import-outside-toplevel
            from .v7 import DreamviewV7
            from .v11 import DreamviewV11

            version = validate_apollo_version(getattr(ctn, "version", 11))
            implementation = DreamviewV7 if version == 7 else DreamviewV11
            return implementation(
                ctn,
                auto_reconnect=auto_reconnect,
                reconnect_attempts=reconnect_attempts,
            )
        return super().__call__(
            ctn,
            auto_reconnect=auto_reconnect,
            reconnect_attempts=reconnect_attempts,
        )


class DreamviewBase(metaclass=_DreamviewMeta):
    """Shared connection handling for Dreamview protocol implementations."""

    def __init__(
        self,
        ctn: Any,
        *,
        auto_reconnect: bool = True,
        reconnect_attempts: int = 1,
    ) -> None:
        """Initialize a Dreamview client."""
        if reconnect_attempts < 0:
            raise ValueError("reconnect_attempts must be non-negative")
        self.ctn = ctn
        self.version: ApolloVersion = validate_apollo_version(
            getattr(ctn, "version", 11)
        )
        self.auto_reconnect = auto_reconnect
        self.reconnect_attempts = reconnect_attempts
        self.socket_client: Any | None = None

    def _hmi_action_payload(
        self, action: str, value: str, request_id: str
    ) -> dict[str, Any]:
        """Build a version-specific HMI request payload."""
        raise NotImplementedError

    def _log_prefix(self) -> str:
        return container_log_prefix(self.ctn)

    def ws_address(self) -> str:
        """Return the Dreamview WebSocket URL."""
        return f"ws://{self.ctn.ip_address}:8888/websocket"

    def connect(self) -> None:
        """Open the Dreamview WebSocket connection."""
        logger.info("{} dreamview connect", self._log_prefix())
        try:
            self.socket_client = create_connection(self.ws_address())
        except (OSError, WebSocketException) as exc:
            self.socket_client = None
            raise DreamviewConnectionError(
                f"Failed to connect to Dreamview at {self.ws_address()}"
            ) from exc
        logger.info("{} dreamview connected", self._log_prefix())

    def close(self) -> None:
        """Close the Dreamview WebSocket connection if one is open."""
        socket_client = self.socket_client
        self.socket_client = None
        if socket_client is None:
            return
        try:
            socket_client.close()
        except (OSError, WebSocketException):
            logger.debug("{} dreamview close failed", self._log_prefix())

    def reconnect(self) -> None:
        """Close the current WebSocket and open a fresh connection."""
        logger.warning("{} dreamview reconnect", self._log_prefix())
        self.close()
        self.connect()

    def _socket(self) -> Any:
        if self.socket_client is None:
            raise RuntimeError("Dreamview WebSocket is not connected")
        return self.socket_client

    @staticmethod
    def _is_connection_error(exc: Exception) -> bool:
        return isinstance(
            exc,
            (
                BrokenPipeError,
                ConnectionError,
                ConnectionResetError,
                OSError,
                WebSocketConnectionClosedException,
            ),
        )

    def _handle_connection_failure(
        self, exc: Exception, attempts_used: int
    ) -> None:
        if not self._is_connection_error(exc):
            raise exc
        if not self.auto_reconnect or attempts_used >= self.reconnect_attempts:
            self.close()
            raise DreamviewConnectionError(
                "Dreamview WebSocket connection lost"
            ) from exc
        self.reconnect()

    def _send_payload(self, payload: dict[str, Any]) -> None:
        attempts_used = 0
        data = json.dumps(payload)
        while True:
            try:
                self._socket().send(data)
                return
            except Exception as exc:  # pylint: disable=broad-exception-caught
                self._handle_connection_failure(exc, attempts_used)
                attempts_used += 1

    def _recv_json(self) -> dict[str, Any]:
        response = self._socket().recv()
        return cast(dict[str, Any], json.loads(response))

    def _send_and_wait_for_response(
        self,
        payload: dict[str, Any],
        is_expected_response: Callable[[dict[str, Any]], bool],
    ) -> dict[str, Any]:
        attempts_used = 0
        while True:
            self._send_payload(payload)
            while True:
                try:
                    response_json = self._recv_json()
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    self._handle_connection_failure(exc, attempts_used)
                    attempts_used += 1
                    break
                if is_expected_response(response_json):
                    return response_json

    def set_mode(self, mode: str) -> None:
        """Set the active Dreamview mode."""
        assert mode in DreamviewModes.__dict__.values(), (
            f"Unsupported mode: {mode}"
        )
        payload = self._hmi_action_payload("CHANGE_MODE", mode, "noResponse")
        logger.info("{} set mode {}", self._log_prefix(), mode)
        self._send_payload(payload)

    def start_module(self, module_name: str) -> None:
        """Request Dreamview to start a module."""
        request_id = nanoid.generate()
        payload = self._hmi_action_payload(
            "START_MODULE", module_name, f"HMIAction!{request_id}"
        )
        logger.info("{} start module {}", self._log_prefix(), module_name)
        self._send_payload(payload)

    def stop_module(self, module_name: str) -> None:
        """Request Dreamview to stop a module."""
        request_id = nanoid.generate()
        payload = self._hmi_action_payload(
            "STOP_MODULE", module_name, f"HMIAction!{request_id}"
        )
        logger.info("{} stop module {}", self._log_prefix(), module_name)
        self._send_payload(payload)

    def set_vehicle(self, vehicle: str) -> dict[str, Any]:
        """Set the active Dreamview vehicle profile."""
        assert vehicle in [
            "Kitti 140",
            "Mkz 121",
            "Mkz Example",
            "Mkz Lgsvl 321",
            "Nuscenes 165",
        ]
        payload = self._hmi_action_payload(
            "CHANGE_VEHICLE", vehicle, "noResponse"
        )
        logger.info("{} set vehicle {}", self._log_prefix(), vehicle)
        response_json = self._send_and_wait_for_response(
            payload, lambda response: response.get("type") == "VehicleParam"
        )
        logger.info("{} vehicle set {}", self._log_prefix(), vehicle)
        return response_json

    @staticmethod
    def _validate_waypoints(waypoints: list[dict[str, float]]) -> bool:
        return bool(waypoints) and all(
            all(key in waypoint for key in ("x", "y", "heading"))
            for waypoint in waypoints
        )

    def set_operation(self, operation: str) -> bool:
        """Set the active Dreamview operation."""
        raise NotImplementedError

    def check_routing_point(self, x: float, y: float, heading: float) -> bool:
        """Check whether a routing point is legal."""
        raise NotImplementedError

    def set_start_point(self, x: float, y: float, heading: float) -> bool:
        """Set the simulation start point."""
        raise NotImplementedError

    def start_routing(self, waypoints: list[dict[str, float]]) -> bool:
        """Send a routing request."""
        raise NotImplementedError

    def load_dynamic_models(self) -> None:
        """Request available dynamic models."""
        raise NotImplementedError

    def change_dynamic_model(self) -> None:
        """Switch to the default dynamic model."""
        raise NotImplementedError

    def set_up_for_sim_control(self) -> dict[str, Any]:
        """Configure Dreamview for simulation control."""
        raise NotImplementedError
