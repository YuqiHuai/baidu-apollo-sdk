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
