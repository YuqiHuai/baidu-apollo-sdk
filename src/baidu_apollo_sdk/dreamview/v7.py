"""Apollo v7 Dreamview protocol implementation."""

from typing import Any

from baidu_apollo_sdk.logging import get_logger

from .base import (
    DreamviewBase,
    DreamviewModes,
    DreamviewOperations,
    DreamviewVehicles,
)

logger = get_logger()


def get_hmi_action_request_payload_v7(
    action: str, value: str, request_id: str
) -> dict[str, Any]:
    """Build an Apollo v7 flat HMI action payload."""
    del request_id
    return {"type": "HMIAction", "action": action, "value": value}


class DreamviewV7(DreamviewBase):
    """Client for the Apollo v7 Dreamview WebSocket protocol."""

    def __init__(
        self,
        ctn: Any,
        *,
        auto_reconnect: bool = True,
        reconnect_attempts: int = 1,
    ) -> None:
        super().__init__(
            ctn,
            auto_reconnect=auto_reconnect,
            reconnect_attempts=reconnect_attempts,
        )
        self._start_point: dict[str, float] | None = None

    def _hmi_action_payload(
        self, action: str, value: str, request_id: str
    ) -> dict[str, Any]:
        return get_hmi_action_request_payload_v7(action, value, request_id)

    def set_operation(self, operation: str) -> bool:
        """Enable v7 simulation control."""
        assert operation in DreamviewOperations.__dict__.values(), (
            f"Unsupported operation: {operation}"
        )
        if operation != DreamviewOperations.SIM_CONTROL:
            raise ValueError(
                f"Dreamview operation {operation!r} is not supported "
                "by Apollo v7"
            )
        self._send_payload({"type": "ToggleSimControl", "enable": True})
        return True

    def check_routing_point(self, x: float, y: float, heading: float) -> bool:
        """Check a routing point using the v7 response type."""
        payload = {
            "type": "CheckRoutingPoint",
            "point": {"x": x, "y": y, "heading": heading, "id": 0},
        }
        response_json = self._send_and_wait_for_response(
            payload,
            lambda response: response.get("type") == "RoutingPointCheckResult",
        )
        return "error" not in response_json

    def set_start_point(self, x: float, y: float, heading: float) -> bool:
        """Store the checked start point for the next v7 routing request."""
        if not self.check_routing_point(x, y, heading):
            return False
        self._start_point = {"x": x, "y": y, "heading": heading}
        return True

    def start_routing(self, waypoints: list[dict[str, float]]) -> bool:
        """Send a v7 routing request containing the stored start point."""
        if not self._validate_waypoints(waypoints):
            logger.error("{} route has invalid waypoints", self._log_prefix())
            return False
        for waypoint in waypoints:
            if not self.check_routing_point(
                waypoint["x"], waypoint["y"], waypoint["heading"]
            ):
                logger.error(
                    "{} route illegal waypoint {}", self._log_prefix(), waypoint
                )
                return False
        if self._start_point is None:
            raise RuntimeError(
                "Apollo v7 routing requires set_start_point() first"
            )
        self._send_payload(
            {
                "type": "SendRoutingRequest",
                "start": self._start_point,
                "waypoint": waypoints[:-1],
                "end": waypoints[-1],
            }
        )
        return True

    def load_dynamic_models(self) -> None:
        """Reject Dreamview+ dynamic-model commands for v7."""
        raise ValueError("Dynamic models are not supported by Apollo v7")

    def change_dynamic_model(self) -> None:
        """Reject Dreamview+ dynamic-model commands for v7."""
        raise ValueError("Dynamic models are not supported by Apollo v7")

    def set_up_for_sim_control(self) -> dict[str, Any]:
        """Configure Apollo v7 simulation control."""
        self.set_mode(DreamviewModes.PNC)
        self.set_operation(DreamviewOperations.SIM_CONTROL)
        return self.set_vehicle(DreamviewVehicles.MKZ_EXAMPLE)
