import json
from typing import Any, cast

import nanoid
from loguru import logger
from websocket import create_connection


class DreamviewModes:
    PNC = "Pnc"
    DEFAULT = "Default"
    PERCEPTION = "Perception"
    VEHICLE_TEST = "Vehicle Test"


class DreamviewOperations:
    SIM_CONTROL = "Sim_Control"
    RECORD = "Record"


class DreamviewVehicles:
    KITTI_140 = "Kitti 140"
    MKZ_121 = "Mkz 121"
    MKZ_EXAMPLE = "Mkz Example"
    MKZ_LGSVL_321 = "Mkz Lgsvl 321"
    NUSCENES_165 = "Nuscenes 165"


def get_hmi_action_request_payload(
    action: str, value: str, request_id: str
) -> dict[str, Any]:
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
    def __init__(self, ctn: Any) -> None:
        self.ctn = ctn
        self.socket_client: Any | None = None

    def ws_address(self) -> str:
        return f"ws://{self.ctn.ip_address}:8888/websocket"

    def connect(self) -> None:
        logger.info(f"{self.ctn.ip_address}: Connecting to Dreamview WebSocket")
        self.socket_client = create_connection(self.ws_address())
        logger.info(f"{self.ctn.ip_address}: Connected to Dreamview WebSocket")

    def _socket(self) -> Any:
        if self.socket_client is None:
            raise RuntimeError("Dreamview WebSocket is not connected")
        return self.socket_client

    def set_mode(self, mode: str) -> None:
        assert mode in DreamviewModes.__dict__.values(), f"Unsupported mode: {mode}"
        payload = get_hmi_action_request_payload("CHANGE_MODE", mode, "noResponse")
        logger.info(f"{self.ctn.ip_address}: Switching Dreamview mode to {mode}")
        self._socket().send(json.dumps(payload))

    def start_module(self, module_name: str) -> None:
        _request_id = nanoid.generate()
        payload = get_hmi_action_request_payload(
            "START_MODULE", module_name, f"HMIAction!{_request_id}"
        )
        logger.info(f"{self.ctn.ip_address}: Starting module {module_name}")
        self._socket().send(json.dumps(payload))

    def stop_module(self, module_name: str) -> None:
        _request_id = nanoid.generate()
        payload = get_hmi_action_request_payload(
            "STOP_MODULE", module_name, f"HMIAction!{_request_id}"
        )
        logger.info(f"{self.ctn.ip_address}: Stopping module {module_name}")
        self._socket().send(json.dumps(payload))

    def set_operation(self, operation: str) -> bool:
        assert operation in DreamviewOperations.__dict__.values(), (
            f"Unsupported operation: {operation}"
        )
        _request_id = nanoid.generate()
        payload = get_hmi_action_request_payload(
            "CHANGE_OPERATION", operation, f"HMIAction!{_request_id}"
        )
        # send the request
        logger.info(
            f"{self.ctn.ip_address}: Setting Dreamview operation to {operation}"
        )
        self._socket().send(json.dumps(payload))
        # Wait for the matching HMIAction response.
        while True:
            response = self._socket().recv()
            response_json = json.loads(response)
            if (
                response_json.get("action") == "response"
                and response_json.get("data", {}).get("requestId")
                == f"HMIAction!{_request_id}"
            ):
                # Warn when Dreamview returns a failed operation response.
                if (
                    response_json.get("data", {})
                    .get("info", {})
                    .get("data", {})
                    .get("isOk", False)
                ):
                    logger.info(
                        f"{self.ctn.ip_address}: Set Dreamview operation to {operation}"
                    )
                else:
                    message = (
                        response_json.get("data", {})
                        .get("info", {})
                        .get("data", {})
                        .get("message", "")
                    )
                    logger.warning(
                        f"{self.ctn.ip_address}: Failed to set Dreamview "
                        f"operation to {operation}. Reason: {message}"
                    )
                return True

    def set_vehicle(self, vehicle: str) -> dict[str, Any]:
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
        logger.info(f"{self.ctn.ip_address}: Setting Dreamview vehicle to {vehicle}")
        self._socket().send(json.dumps(payload))
        # wait for the response
        while True:
            response = self._socket().recv()
            response_json = json.loads(response)
            if response_json.get("type") == "VehicleParam":
                logger.info(
                    f"{self.ctn.ip_address}: Set Dreamview vehicle to {vehicle}"
                )
                return cast(dict[str, Any], response_json)

    def check_routing_point(self, x: float, y: float, heading: float) -> bool:
        _request_id = nanoid.generate()
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
                "requestId": f"CheckRoutingPoint!{_request_id}",
            },
            "type": "CheckRoutingPoint",
            "action": "request",
        }
        logger.info(
            f"{self.ctn.ip_address}: Checking routing point ({x}, {y}, {heading})"
        )
        self._socket().send(json.dumps(payload))
        # wait for the response
        while True:
            response = self._socket().recv()
            response_json = json.loads(response)
            # Wait for the matching CheckRoutingPoint response.
            if (
                response_json.get("action") == "response"
                and response_json.get("data", {}).get("requestId")
                == f"CheckRoutingPoint!{_request_id}"
            ):
                # data.info.data.isLegao == 1
                is_legal = bool(
                    cast(
                        dict[str, Any],
                        response_json.get("data", {}).get("info", {}).get("data", {}),
                    ).get("isLegal", 0)
                    == 1
                )
                if is_legal:
                    logger.info(f"{self.ctn.ip_address}: Routing point is legal")
                if not is_legal:
                    message = (
                        response_json.get("data", {}).get("info", {}).get("message", "")
                    )
                    logger.warning(
                        f"{self.ctn.ip_address}: Routing point is illegal. "
                        f"Reason: {message}"
                    )
                return is_legal

    def set_start_point(self, x: float, y: float, heading: float) -> bool:
        _request_id = nanoid.generate()
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
                "requestId": f"SetStartPoint!{_request_id}",
            },
            "type": "SetStartPoint",
            "action": "request",
        }
        # check the point legality first
        if not self.check_routing_point(x, y, heading):
            logger.error(
                f"{self.ctn.ip_address}: Failed to set start point to "
                f"({x}, {y}, {heading}) due to illegal point"
            )
            return False
        # send the request
        logger.info(
            f"{self.ctn.ip_address}: Setting start point to ({x}, {y}, {heading})"
        )
        self._socket().send(json.dumps(payload))
        # wait for the response
        while True:
            response = self._socket().recv()
            response_json = json.loads(response)

            # Wait for the matching SetStartPoint response.
            if (
                response_json.get("action") == "response"
                and response_json.get("data", {}).get("requestId")
                == f"SetStartPoint!{_request_id}"
            ):
                # check response.data.code.info == -1 for failure
                if response_json.get("data", {}).get("info", {}).get("code", 0) == -1:
                    message = (
                        response_json.get("data", {}).get("info", {}).get("message", "")
                    )
                    logger.error(
                        f"{self.ctn.ip_address}: Failed to set start point. "
                        f"Reason: {message}"
                    )
                    return False
                else:
                    logger.info(f"{self.ctn.ip_address}: Set start point successfully")
                    return True

    def start_routing(self, waypoints: list[dict[str, float]]) -> bool:
        # validate input shape first
        for waypoint in waypoints:
            if not all(k in waypoint for k in ("x", "y", "heading")):
                logger.error(
                    f"{self.ctn.ip_address}: Failed to start routing due to "
                    f"illegal waypoint format: {waypoint}"
                )
                return False
        # validate waypoints are valid routing points
        for waypoint in waypoints:
            if not self.check_routing_point(
                waypoint["x"], waypoint["y"], waypoint["heading"]
            ):
                waypoint_text = (
                    f"({waypoint['x']}, {waypoint['y']}, {waypoint['heading']})"
                )
                logger.error(
                    f"{self.ctn.ip_address}: Failed to start routing due to "
                    f"illegal waypoint {waypoint_text}"
                )
                return False
        _request_id = nanoid.generate()
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
                "requestId": f"SendRoutingRequest!{_request_id}",
            },
            "type": "SendRoutingRequest",
            "action": "request",
        }
        logger.info(
            f"{self.ctn.ip_address}: Starting routing with {len(waypoints)} waypoints"
        )
        self._socket().send(json.dumps(payload))
        # wait for response
        while True:
            response = self._socket().recv()
            response_json = json.loads(response)

            # Wait for the matching SendRoutingRequest response.
            if (
                response_json.get("action") == "response"
                and response_json.get("data", {}).get("requestId")
                == f"SendRoutingRequest!{_request_id}"
            ):
                # check response.data.code.info == -1 for failure
                if response_json.get("data", {}).get("info", {}).get("code", 0) == -1:
                    message = (
                        response_json.get("data", {}).get("info", {}).get("message", "")
                    )
                    logger.error(
                        f"{self.ctn.ip_address}: Failed to start routing. "
                        f"Reason: {message}"
                    )
                    return False
                else:
                    logger.info(f"{self.ctn.ip_address}: Started routing successfully")
                    return True

    def load_dynamic_models(self) -> None:
        payload = get_hmi_action_request_payload(
            "LOAD_DYNAMIC_MODELS", "", "noResponse"
        )
        logger.info(f"{self.ctn.ip_address}: Loading dynamic models")
        self._socket().send(json.dumps(payload))

    def change_dynamic_model(self) -> None:
        payload = get_hmi_action_request_payload(
            "CHANGE_DYNAMIC_MODEL", "Simulation Perfect Control", "noResponse"
        )
        logger.info(
            f"{self.ctn.ip_address}: Changing dynamic model to "
            "Simulation Perfect Control"
        )
        self._socket().send(json.dumps(payload))
    
    def set_up_for_sim_control(self) -> dict[str, Any]:
        self.set_mode(DreamviewModes.PNC)
        self.set_operation(DreamviewOperations.SIM_CONTROL)
        self.load_dynamic_models()
        self.change_dynamic_model()
        return self.set_vehicle(DreamviewVehicles.MKZ_EXAMPLE)
