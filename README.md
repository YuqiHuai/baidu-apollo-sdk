# apollo_instance

## Development

Install dependencies:

```bash
uv sync --dev
```

Run linting and formatting checks:

```bash
uv run ruff check .
uv run ruff format --check .
```

Run type checks:

```bash
uv run mypy
```

Run tests:

```bash
uv run pytest
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
`apollo_dev_apollo_instance_test`, then stop and remove it after the integration
tests finish. Override the container suffix with `APOLLO_TEST_CONTAINER_NAME`:

```bash
APOLLO_TEST_CONTAINER_NAME=your_name uv run pytest -m integration
```

Do not use `APOLLO_TEST_CONTAINER_NAME=yuqi`; the tests reject that name to avoid
touching a personal development container. If Docker or config is unavailable,
integration tests are skipped instead of failing.
