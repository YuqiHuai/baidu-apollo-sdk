"""Send one v11 action request to the HTTP bridge inside Apollo."""

import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from baidu_apollo_sdk.apollo_container import ApolloContainer

APOLLO_V11_PATH = Path("/home/yuqi/ResearchWorkspace/ICSE_2027/apollo-v11.0.0")
ACTION_COMMAND = "PULL_OVER"


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
    """Send one action command through the Apollo v11 HTTP bridge."""
    container = ApolloContainer("yuqi", APOLLO_V11_PATH, version=11)
    response = _post_json(
        f"http://{container.ip_address}:9091/action",
        {"command": ACTION_COMMAND},
    )
    print(response)
    print(
        "Sent Apollo v11 action request to "
        f"{container.container_name} at {container.ip_address}:9091"
    )


if __name__ == "__main__":
    main()
