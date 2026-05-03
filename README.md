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

Integration tests require Docker, a valid `.env`, and an already-running Apollo
development container. By default, tests look for the Apollo container named
`apollo_dev_yuqi`, because the test container name defaults to `yuqi`. Override
the container suffix with `APOLLO_TEST_CONTAINER_NAME`:

```bash
APOLLO_TEST_CONTAINER_NAME=your_name uv run pytest -m integration
```

If Docker, config, or the container is unavailable, integration tests are skipped
instead of failing.
