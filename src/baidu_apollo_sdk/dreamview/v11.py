"""Apollo v11 Dreamview+ protocol implementation."""

from typing import Any, cast

import nanoid

from baidu_apollo_sdk.logging import get_logger

from .base import (
    DreamviewBase,
    DreamviewModes,
    DreamviewOperations,
    DreamviewVehicles,
)

logger = get_logger()


def get_hmi_action_request_payload_v11(
    action: str, value: str, request_id: str
) -> dict[str, Any]:
    """Build an Apollo v11 Dreamview+ HMI request payload."""
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


class DreamviewV11(DreamviewBase):
    """Client for the Apollo v11 Dreamview+ WebSocket protocol."""

    def _hmi_action_payload(
        self, action: str, value: str, request_id: str
    ) -> dict[str, Any]:
        return get_hmi_action_request_payload_v11(action, value, request_id)

    def set_operation(self, operation: str) -> bool:
        """Set the active Dreamview+ operation."""
        assert operation in DreamviewOperations.__dict__.values(), (
            f"Unsupported operation: {operation}"
        )
        request_id = nanoid.generate()
        payload = self._hmi_action_payload(
            "CHANGE_OPERATION", operation, f"HMIAction!{request_id}"
        )
        logger.info("{} set operation {}", self._log_prefix(), operation)
        response_json = self._send_and_wait_for_response(
            payload,
            lambda response: (
                response.get("action") == "response"
                and response.get("data", {}).get("requestId")
                == f"HMIAction!{request_id}"
            ),
        )
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

    def check_routing_point(self, x: float, y: float, heading: float) -> bool:
        """Check whether a Dreamview+ routing point is legal."""
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
            lambda response: (
                response.get("action") == "response"
                and response.get("data", {}).get("requestId")
                == f"CheckRoutingPoint!{request_id}"
            ),
        )
        is_legal = bool(
            cast(
                dict[str, Any],
                response_json.get("data", {}).get("info", {}).get("data", {}),
            ).get("isLegal", 0)
            == 1
        )
        if not is_legal:
            message = (
                response_json.get("data", {}).get("info", {}).get("message", "")
            )
            logger.warning(
                "{} route point illegal: {}", self._log_prefix(), message
            )
        return is_legal

    def set_start_point(self, x: float, y: float, heading: float) -> bool:
        """Set the Dreamview+ simulation start point."""
        request_id = nanoid.generate()
        payload = {
            "data": {
                "name": "",
                "info": {"point": {"x": x, "y": y, "heading": heading}},
                "source": "dreamview",
                "target": "dreamview",
                "sourceType": "module",
                "targetType": "dreamview",
                "requestId": f"SetStartPoint!{request_id}",
            },
            "type": "SetStartPoint",
            "action": "request",
        }
        if not self.check_routing_point(x, y, heading):
            logger.error(
                "{} start point illegal ({}, {}, {})",
                self._log_prefix(),
                x,
                y,
                heading,
            )
            return False
        response_json = self._send_and_wait_for_response(
            payload,
            lambda response: (
                response.get("action") == "response"
                and response.get("data", {}).get("requestId")
                == f"SetStartPoint!{request_id}"
            ),
        )
        if response_json.get("data", {}).get("info", {}).get("code", 0) == -1:
            return False
        return True

    def start_routing(self, waypoints: list[dict[str, float]]) -> bool:
        """Send a Dreamview+ routing request."""
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
        response_json = self._send_and_wait_for_response(
            payload,
            lambda response: (
                response.get("action") == "response"
                and response.get("data", {}).get("requestId")
                == f"SendRoutingRequest!{request_id}"
            ),
        )
        return bool(
            response_json.get("data", {}).get("info", {}).get("code", 0) != -1
        )

    def load_dynamic_models(self) -> None:
        """Request Dreamview+ to load available dynamic models."""
        payload = self._hmi_action_payload(
            "LOAD_DYNAMIC_MODELS", "", "noResponse"
        )
        self._send_payload(payload)

    def change_dynamic_model(self) -> None:
        """Switch Dreamview+ to Simulation Perfect Control."""
        payload = self._hmi_action_payload(
            "CHANGE_DYNAMIC_MODEL", "Simulation Perfect Control", "noResponse"
        )
        self._send_payload(payload)

    def set_up_for_sim_control(self) -> dict[str, Any]:
        """Configure Dreamview+ simulation control."""
        self.set_mode(DreamviewModes.PNC)
        self.set_operation(DreamviewOperations.SIM_CONTROL)
        self.load_dynamic_models()
        self.change_dynamic_model()
        return self.set_vehicle(DreamviewVehicles.MKZ_EXAMPLE)
