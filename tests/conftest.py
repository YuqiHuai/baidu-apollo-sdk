from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any

import docker
import pytest

from apollo_instance.apollo_container import ApolloContainer
from apollo_instance.apollo_repo import ApolloRepo

APOLLO_TEST_CONTAINER_NAME_ENV = "APOLLO_TEST_CONTAINER_NAME"
DEFAULT_APOLLO_TEST_CONTAINER_NAME = "apollo_instance_test"


def remove_docker_container(docker_client: Any, container_name: str) -> None:
    try:
        docker_container = docker_client.containers.get(container_name)
    except docker.errors.NotFound:
        return
    docker_container.remove(force=True)


@pytest.fixture(scope="session")
def apollo_test_container() -> Iterator[ApolloContainer]:
    try:
        repo = ApolloRepo.from_config()
    except RuntimeError as exc:
        pytest.skip(str(exc))

    container_name = os.environ.get(
        APOLLO_TEST_CONTAINER_NAME_ENV,
        DEFAULT_APOLLO_TEST_CONTAINER_NAME,
    )
    if container_name == "yuqi":
        pytest.fail(
            f"{APOLLO_TEST_CONTAINER_NAME_ENV}=yuqi would target a personal "
            "development container. Use a dedicated test container name."
        )

    full_container_name = ApolloContainer.DEV_CONTAINER_PREFIX + container_name
    try:
        docker_client = docker.from_env()
        docker_client.ping()
    except docker.errors.DockerException as exc:
        pytest.skip(f"Docker is not available: {exc}")

    remove_docker_container(docker_client, full_container_name)
    container = ApolloContainer(container_name, str(repo.get_path()))

    try:
        container.start()
        yield container
    finally:
        remove_docker_container(docker_client, full_container_name)
