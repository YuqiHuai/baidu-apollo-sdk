"""Public Dreamview client facade for supported Apollo versions."""

from typing import Any

from baidu_apollo_sdk.version import validate_apollo_version

from .base import (
    DreamviewBase,
    DreamviewConnectionError,
    DreamviewModes,
    DreamviewOperations,
    DreamviewVehicles,
)
from .v7 import get_hmi_action_request_payload_v7
from .v11 import get_hmi_action_request_payload_v11


def get_hmi_action_request_payload(
    action: str, value: str, request_id: str, version: int = 11
) -> dict[str, Any]:
    """Build an HMI request payload for an Apollo Dreamview version."""
    if validate_apollo_version(version) == 7:
        return get_hmi_action_request_payload_v7(action, value, request_id)
    return get_hmi_action_request_payload_v11(action, value, request_id)


Dreamview = DreamviewBase
"""Backward-compatible constructor for a version-specific Dreamview client."""


__all__ = [
    "Dreamview",
    "DreamviewBase",
    "DreamviewConnectionError",
    "DreamviewModes",
    "DreamviewOperations",
    "DreamviewVehicles",
    "get_hmi_action_request_payload",
]
