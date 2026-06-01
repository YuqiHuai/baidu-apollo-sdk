"""Send one v11 parking request to the HTTP bridge inside Apollo."""

import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from baidu_apollo_sdk.apollo_container import ApolloContainer
from baidu_apollo_sdk.apollo_runtime import ApolloRuntime
from baidu_apollo_sdk.commands import Pose
from baidu_apollo_sdk.dreamview import Dreamview

APOLLO_V11_PATH = Path("/home/yuqi/ResearchWorkspace/ICSE_2027/apollo-v11.0.0")
PARKING_SPOT_ID = "11545"
START_POSE = Pose(
    x=587178.461623482,
    y=4141425.760698328,
    heading=-0.207496226,
)


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request) as response:  # noqa: S310
            response_body = response.read()
    except HTTPError as exc:
        response_body = exc.read()
    if not response_body:
        return None
    return json.loads(response_body.decode("utf-8"))


def main() -> None:
    """Send one valet-parking request through the Apollo v11 HTTP bridge."""
    container = ApolloContainer("yuqi", APOLLO_V11_PATH, version=11)
    runtime = ApolloRuntime(container)
    runtime.bootstrap()

    dreamview = Dreamview(container)
    dreamview.connect()
    dreamview.set_start_point(
        START_POSE.x,
        START_POSE.y,
        START_POSE.heading or 0.0,
    )

    response = _post_json(
        f"http://{container.ip_address}:9091/valet_parking",
        {"parking_spot_id": PARKING_SPOT_ID},
    )
    print(response)
    print(
        "Sent Apollo v11 parking request to "
        f"{container.container_name} at {container.ip_address}:9091"
    )


if __name__ == "__main__":
    main()
