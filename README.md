# baidu_apollo_sdk

## Development

Install dependencies:

```bash
uv sync --dev
```

Run linting and formatting checks:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pylint --rcfile=pylintrc src/baidu_apollo_sdk
```

Run type checks:

```bash
uv run mypy
```

Run tests:

```bash
uv run pytest
```

Build documentation:

```bash
uv run sphinx-build -W -b html docs docs/_build/html
```

Run tests without integration cases:

```bash
uv run pytest -m "not integration"
```

Run only integration cases:

```bash
uv run pytest -m integration
```

Integration tests require Docker and a valid `.env`. They create a dedicated
Apollo development container for the test session and remove any stale container
with the same name before starting. By default, tests use
`apollo_dev_baidu_apollo_sdk_test`, then stop and remove it after the integration
tests finish. Override the container suffix with `APOLLO_TEST_CONTAINER_NAME`:

```bash
APOLLO_TEST_CONTAINER_NAME=your_name uv run pytest -m integration
```

Do not use `APOLLO_TEST_CONTAINER_NAME=yuqi`; the tests reject that name to avoid
touching a personal development container. If Docker or config is unavailable,
integration tests are skipped instead of failing.

## CyberRT examples

Apollo v11 remains the default. For an Apollo v7 container, select matching
protobuf topics before publishing or subscribing:

```python
from baidu_apollo_sdk.cyber_rt.topics import get_topics

topics = get_topics(container.version)
latest_loc = bridge_client.subscribe_latest(topic=topics.LocalizationTopic)
```

Use one Apollo protobuf version per Python process. The generated v7 and v11
schemas contain overlapping descriptors and cannot be loaded together.

Subscribe to the latest localization message and decode the raw CyberRT bytes
with the topic decoder:

```bash
uv run python examples/subscribe_localization.py
```

The example stores the latest value with `subscribe_latest()` and decodes it via
`Topics.LocalizationTopic.decoder(raw)`.

Stream localization messages as they arrive with `subscribe()`:

```bash
uv run python examples/stream_localization.py
```

The streaming example iterates over raw message bytes and decodes each message
with `Topics.LocalizationTopic.decoder(raw)`.

Subscribe to the latest values from multiple topics in one loop:

```bash
uv run python examples/subscribe_multiple_latest.py
```

The multi-topic example uses `subscribe_latest()` for localization and chassis,
then decodes each raw message with that topic's decoder.

Publish traffic light detections:

```bash
uv run python examples/publish_traffic_light.py
```

The publish example builds a `TrafficLightDetection` protobuf message, serializes
it with `SerializeToString()`, and publishes the bytes with
`bridge_client.publish(topic=Topics.TrafficLightTopic, msg=raw)`.

Run a Dreamview simulation-control scenario:

```bash
uv run python examples/run_dreamview_scenario.py
```

The Dreamview scenario starts the development container, configures the
`borregas_ave` map, starts planning, records a short route, and prints the
Dreamview URL.

## Commands

Send a lane-follow command. Apollo v11 uses the HTTP bridge; Apollo v7 uses
CyberRT publications:

```python
from baidu_apollo_sdk.commands import CommandSender, LaneFollowCommand, Pose

sender = CommandSender(
    None,
    version=11,
    lane_follow_service_url=f"http://{container.ip_address}:9091",
)
response = sender.send_lane_follow(
    LaneFollowCommand(
        start_pose=Pose(x=587202.0, y=4141420.0, heading=0.0),
        end_pose=Pose(x=587223.0, y=4141416.0, heading=0.0),
        command_id=5,
    )
)
print(response)
```

Parking commands additionally need a loaded map service. The sender resolves
the parking polygon, derives the routing endpoint, and publishes the polygon
center and corners. Apollo v7 parking commands publish
`/apollo/routing_request`, wait briefly, then publish `/apollo/task_manager`.
The task-manager message also embeds the derived routing request:

```python
from baidu_apollo_sdk.commands import ParkingCommand

sender = CommandSender(
    bridge_client,
    version=container.version,
    map_service=map_service,
)
sender.send_parking(
    ParkingCommand(
        initial_pose=Pose(x=587178.0, y=4141425.0),
        parking_space_id="11545",
    )
)
```

Apollo v7 consumes the routing request directly. Apollo v11 lane follow uses
the custom HTTP bridge on the Apollo container IP at port `9091`, while
parking still uses the `external_command_with_old_routing.launch`
compatibility adapter because cyber-bridge publishes messages but does not
invoke Cyber service endpoints.

With cyber-bridge already running in `apollo_dev_yuqi`, send the Apollo v7
live-test requests with:

```bash
uv run python examples/v7/test_send_v7_routing_request.py
uv run python examples/v7/test_send_v7_parking_request.py
uv run python examples/v11/test_send_v11_lane_follow_request.py
uv run python examples/v11/test_send_v11_action_request.py
uv run python examples/v11/test_send_v11_parking_request.py
```
