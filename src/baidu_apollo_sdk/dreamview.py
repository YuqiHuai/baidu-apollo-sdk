"""Dreamview WebSocket client helpers."""

import json
from collections.abc import Callable
from typing import Any, cast

import nanoid
from websocket import (
    WebSocketConnectionClosedException,
    WebSocketException,
    create_connection,
)

from baidu_apollo_sdk.logging import container_log_prefix, get_logger

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


def get_hmi_action_request_payload(
    action: str, value: str, request_id: str
) -> dict[str, Any]:
    """Build a Dreamview HMI action request payload.

    Args:
        action: Dreamview HMI action name.
        value: Action value to send in the payload.
        request_id: Request identifier used to correlate responses.

    Returns:
        JSON-serializable request payload.
    """
    return {
        "data": {
            "name": "",
            "info": {"action": action, "value": value},
            "source": "dreamview",
            "target": "dreamview",
            "sourceType": "module",
            "targetType": "dreamview",
            "requestId": request_id,
        },
        "type": "HMIAction",
        "action": "request",
    }


class Dreamview:
    """Client for controlling Apollo Dreamview through its WebSocket API.

    Attributes:
        ctn: Container-like object exposing `ip_address`.
        socket_client: WebSocket client after `connect()` succeeds.
    """

    def __init__(
        self,
        ctn: Any,
        *,
        auto_reconnect: bool = True,
        reconnect_attempts: int = 1,
    ) -> None:
        """Initialize a Dreamview client.

        Args:
            ctn: Container-like object with an `ip_address` property.
            auto_reconnect: Whether to reopen the WebSocket after a connection
                failure and retry the in-flight request.
            reconnect_attempts: Maximum reconnect retries per SDK operation.
        """
        if reconnect_attempts < 0:
            raise ValueError("reconnect_attempts must be non-negative")
        self.ctn = ctn
        self.auto_reconnect = auto_reconnect
        self.reconnect_attempts = reconnect_attempts
        self.socket_client: Any | None = None

    def _log_prefix(self) -> str:
        return container_log_prefix(self.ctn)

    def ws_address(self) -> str:
        """Return the Dreamview WebSocket URL.

        Returns:
            WebSocket URL for the configured container.
        """
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
        """Return the connected WebSocket client.

        Returns:
            Active WebSocket client.

        Raises:
            RuntimeError: If `connect()` has not been called successfully.
        """
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
            except Exception as exc:
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
                except Exception as exc:
                    self._handle_connection_failure(exc, attempts_used)
                    attempts_used += 1
                    break
                if is_expected_response(response_json):
                    return response_json

    def set_mode(self, mode: str) -> None:
        """Set the active Dreamview mode.

        Args:
            mode: Dreamview mode value from `DreamviewModes`.

        Raises:
            AssertionError: If the mode is unsupported.
        """
        assert mode in DreamviewModes.__dict__.values(), (
            f"Unsupported mode: {mode}"
        )
        payload = get_hmi_action_request_payload(
            "CHANGE_MODE", mode, "noResponse"
        )
        logger.info("{} set mode {}", self._log_prefix(), mode)
        self._send_payload(payload)

    def start_module(self, module_name: str) -> None:
        """Request Dreamview to start a module.

        Args:
            module_name: Dreamview module name.
        """
        request_id = nanoid.generate()
        payload = get_hmi_action_request_payload(
            "START_MODULE", module_name, f"HMIAction!{request_id}"
        )
        logger.info("{} start module {}", self._log_prefix(), module_name)
        self._send_payload(payload)

    def stop_module(self, module_name: str) -> None:
        """Request Dreamview to stop a module.

        Args:
            module_name: Dreamview module name.
        """
        request_id = nanoid.generate()
        payload = get_hmi_action_request_payload(
            "STOP_MODULE", module_name, f"HMIAction!{request_id}"
        )
        logger.info("{} stop module {}", self._log_prefix(), module_name)
        self._send_payload(payload)

    def set_operation(self, operation: str) -> bool:
        """Set the active Dreamview operation.

        Args:
            operation: Operation value from `DreamviewOperations`.

        Returns:
            True after a matching Dreamview response is received.

        Raises:
            AssertionError: If the operation is unsupported.
        """
        assert operation in DreamviewOperations.__dict__.values(), (
            f"Unsupported operation: {operation}"
        )
        request_id = nanoid.generate()
        payload = get_hmi_action_request_payload(
            "CHANGE_OPERATION", operation, f"HMIAction!{request_id}"
        )
        # send the request
        logger.info("{} set operation {}", self._log_prefix(), operation)
        response_json = self._send_and_wait_for_response(
            payload,
            lambda response: response.get("action") == "response"
            and response.get("data", {}).get("requestId")
            == f"HMIAction!{request_id}",
        )
        # Warn when Dreamview returns a failed operation response.
        if (
            response_json.get("data", {})
            .get("info", {})
            .get("data", {})
            .get("isOk", False)
        ):
            logger.info("{} operation set {}", self._log_prefix(), operation)
        else:
            message = (
                response_json.get("data", {})
                .get("info", {})
                .get("data", {})
                .get("message", "")
            )
            logger.warning(
                "{} operation failed {}: {}",
                self._log_prefix(),
                operation,
                message,
            )
        return True

    def set_vehicle(self, vehicle: str) -> dict[str, Any]:
        """Set the active Dreamview vehicle profile.

        Args:
            vehicle: Vehicle profile name.

        Returns:
            Vehicle parameter response from Dreamview.

        Raises:
            AssertionError: If the vehicle profile is unsupported.
        """
        assert vehicle in [
            "Kitti 140",
            "Mkz 121",
            "Mkz Example",
            "Mkz Lgsvl 321",
            "Nuscenes 165",
        ]
        payload = get_hmi_action_request_payload(
            "CHANGE_VEHICLE", vehicle, "noResponse"
        )
        logger.info("{} set vehicle {}", self._log_prefix(), vehicle)
        response_json = self._send_and_wait_for_response(
            payload, lambda response: response.get("type") == "VehicleParam"
        )
        logger.info("{} vehicle set {}", self._log_prefix(), vehicle)
        return response_json

    def check_routing_point(self, x: float, y: float, heading: float) -> bool:
        """Check whether a routing point is legal in Dreamview.

        Args:
            x: Map x coordinate.
            y: Map y coordinate.
            heading: Vehicle heading in radians.

        Returns:
            True if Dreamview reports the routing point as legal.
        """
        request_id = nanoid.generate()
        payload = {
            "data": {
                "name": "",
                "info": {
                    "point": {
                        "x": x,
                        "y": y,
                        "heading": heading,
                        "id": 0,
                    }
                },
                "source": "dreamview",
                "target": "dreamview",
                "sourceType": "module",
                "targetType": "dreamview",
                "requestId": f"CheckRoutingPoint!{request_id}",
            },
            "type": "CheckRoutingPoint",
            "action": "request",
        }
        logger.info(
            "{} check route point ({}, {}, {})",
            self._log_prefix(),
            x,
            y,
            heading,
        )
        response_json = self._send_and_wait_for_response(
            payload,
            lambda response: response.get("action") == "response"
            and response.get("data", {}).get("requestId")
            == f"CheckRoutingPoint!{request_id}",
        )
        # data.info.data.isLegao == 1
        is_legal = bool(
            cast(
                dict[str, Any],
                response_json.get("data", {}).get("info", {}).get("data", {}),
            ).get("isLegal", 0)
            == 1
        )
        if is_legal:
            logger.info("{} route point legal", self._log_prefix())
        if not is_legal:
            message = (
                response_json.get("data", {})
                .get("info", {})
                .get("message", "")
            )
            logger.warning(
                "{} route point illegal: {}",
                self._log_prefix(),
                message,
            )
        return is_legal

    def set_start_point(self, x: float, y: float, heading: float) -> bool:
        """Set the simulation start point in Dreamview.

        Args:
            x: Map x coordinate.
            y: Map y coordinate.
            heading: Vehicle heading in radians.

        Returns:
            True if Dreamview accepts the start point.
        """
        request_id = nanoid.generate()
        payload = {
            "data": {
                "name": "",
                "info": {
                    "point": {
                        "x": x,
                        "y": y,
                        "heading": heading,
                    }
                },
                "source": "dreamview",
                "target": "dreamview",
                "sourceType": "module",
                "targetType": "dreamview",
                "requestId": f"SetStartPoint!{request_id}",
            },
            "type": "SetStartPoint",
            "action": "request",
        }
        # check the point legality first
        if not self.check_routing_point(x, y, heading):
            logger.error(
                "{} start point illegal ({}, {}, {})",
                self._log_prefix(),
                x,
                y,
                heading,
            )
            return False
        # send the request
        logger.info(
            "{} set start point ({}, {}, {})",
            self._log_prefix(),
            x,
            y,
            heading,
        )
        response_json = self._send_and_wait_for_response(
            payload,
            lambda response: response.get("action") == "response"
            and response.get("data", {}).get("requestId")
            == f"SetStartPoint!{request_id}",
        )
        # check response.data.code.info == -1 for failure
        if response_json.get("data", {}).get("info", {}).get("code", 0) == -1:
            message = (
                response_json.get("data", {}).get("info", {}).get("message", "")
            )
            logger.error(
                "{} start point failed: {}",
                self._log_prefix(),
                message,
            )
            return False
        logger.info("{} start point set", self._log_prefix())
        return True

    def start_routing(self, waypoints: list[dict[str, float]]) -> bool:
        """Send a routing request to Dreamview.

        Args:
            waypoints: Ordered list of waypoints. Each waypoint must contain
                `x`, `y`, and `heading` keys.

        Returns:
            True if Dreamview accepts the route.
        """
        # validate input shape first
        for waypoint in waypoints:
            if not all(k in waypoint for k in ("x", "y", "heading")):
                logger.error(
                    "{} route invalid waypoint {}",
                    self._log_prefix(),
                    waypoint,
                )
                return False
        # validate waypoints are valid routing points
        for waypoint in waypoints:
            if not self.check_routing_point(
                waypoint["x"], waypoint["y"], waypoint["heading"]
            ):
                waypoint_x = waypoint["x"]
                waypoint_y = waypoint["y"]
                waypoint_heading = waypoint["heading"]
                waypoint_text = (
                    f"({waypoint_x}, {waypoint_y}, {waypoint_heading})"
                )
                logger.error(
                    "{} route illegal waypoint {}",
                    self._log_prefix(),
                    waypoint_text,
                )
                return False
        request_id = nanoid.generate()
        payload = {
            "data": {
                "name": "",
                "info": {
                    "waypoint": [
                        {"x": wp["x"], "y": wp["y"], "heading": wp["heading"]}
                        for wp in waypoints[:-1]
                    ],
                    "end": {
                        "x": waypoints[-1]["x"],
                        "y": waypoints[-1]["y"],
                        "heading": waypoints[-1]["heading"],
                    },
                },
                "source": "dreamview",
                "target": "dreamview",
                "sourceType": "module",
                "targetType": "dreamview",
                "requestId": f"SendRoutingRequest!{request_id}",
            },
            "type": "SendRoutingRequest",
            "action": "request",
        }
        logger.info(
            "{} start route {} waypoints",
            self._log_prefix(),
            len(waypoints),
        )
        response_json = self._send_and_wait_for_response(
            payload,
            lambda response: response.get("action") == "response"
            and response.get("data", {}).get("requestId")
            == f"SendRoutingRequest!{request_id}",
        )
        # check response.data.code.info == -1 for failure
        if response_json.get("data", {}).get("info", {}).get("code", 0) == -1:
            message = (
                response_json.get("data", {}).get("info", {}).get("message", "")
            )
            logger.error("{} route failed: {}", self._log_prefix(), message)
            return False
        logger.info("{} route started", self._log_prefix())
        return True

    def load_dynamic_models(self) -> None:
        """Request Dreamview to load available dynamic models."""
        payload = get_hmi_action_request_payload(
            "LOAD_DYNAMIC_MODELS", "", "noResponse"
        )
        logger.info("{} load dynamic models", self._log_prefix())
        self._send_payload(payload)

    def change_dynamic_model(self) -> None:
        """Switch Dreamview to the Simulation Perfect Control dynamic model."""
        payload = get_hmi_action_request_payload(
            "CHANGE_DYNAMIC_MODEL", "Simulation Perfect Control", "noResponse"
        )
        logger.info(
            "{} set dynamic model Simulation Perfect Control",
            self._log_prefix(),
        )
        self._send_payload(payload)

    def set_up_for_sim_control(self) -> dict[str, Any]:
        """Configure Dreamview for simulation control.

        Returns:
            Vehicle parameter response from the final vehicle selection step.
        """
        self.set_mode(DreamviewModes.PNC)
        self.set_operation(DreamviewOperations.SIM_CONTROL)
        self.load_dynamic_models()
        self.change_dynamic_model()
        return self.set_vehicle(DreamviewVehicles.MKZ_EXAMPLE)
