from __future__ import annotations

import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import docker
import pytest

from baidu_apollo_sdk.apollo_container import ApolloContainer


@dataclass
class FakeExecResult:
    output: bytes | list[bytes]


@dataclass
class ExecRunCall:
    command: str
    user: str
    workdir: str
    environment: dict[str, str]
    stream: bool
    detach: bool


@dataclass
class FakeDockerContainer:
    status: str = "running"
    attrs: dict[str, Any] = field(
        default_factory=lambda: {
            "NetworkSettings": {
                "Networks": {
                    "bridge": {
                        "IPAddress": "172.17.0.2",
                    },
                },
            },
        }
    )
    exec_calls: list[ExecRunCall] = field(default_factory=list)
    output: bytes = b"command output"
    stream_output: list[bytes] = field(
        default_factory=lambda: [b"hello", b" world"]
    )

    def exec_run(
        self,
        command: str,
        user: str,
        workdir: str,
        environment: dict[str, str],
        stream: bool,
        detach: bool,
    ) -> FakeExecResult:
        self.exec_calls.append(
            ExecRunCall(
                command=command,
                user=user,
                workdir=workdir,
                environment=environment,
                stream=stream,
                detach=detach,
            )
        )
        if stream:
            return FakeExecResult(self.stream_output)
        return FakeExecResult(self.output)


class FakeContainerCollection:
    def __init__(self, container: FakeDockerContainer | None) -> None:
        self.container = container
        self.requested_names: list[str] = []

    def get(self, name: str) -> FakeDockerContainer:
        self.requested_names.append(name)
        if self.container is None:
            raise docker.errors.NotFound("container not found")
        return self.container


class FakeDockerClient:
    def __init__(self, container: FakeDockerContainer | None) -> None:
        self.containers = FakeContainerCollection(container)


def apollo_container(
    monkeypatch: pytest.MonkeyPatch,
    docker_container: FakeDockerContainer | None = None,
    version: int = 11,
) -> ApolloContainer:
    fake_client = FakeDockerClient(docker_container or FakeDockerContainer())
    monkeypatch.setattr(
        "baidu_apollo_sdk.apollo_container.docker.from_env",
        lambda: fake_client,
    )
    return ApolloContainer("yuqi", "/apollo/root", version=version)


def test_container_name_adds_dev_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = apollo_container(monkeypatch)

    assert container.container_name == "apollo_dev_yuqi"


def test_container_rejects_unsupported_apollo_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(ValueError, match="Unsupported Apollo version"):
        apollo_container(monkeypatch, version=10)


def test_is_running_returns_true_for_running_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = apollo_container(
        monkeypatch, FakeDockerContainer(status="running")
    )

    assert container.is_running() is True


def test_is_running_returns_false_for_stopped_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = apollo_container(
        monkeypatch, FakeDockerContainer(status="exited")
    )

    assert container.is_running() is False


def test_is_running_returns_false_when_container_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = apollo_container(monkeypatch, None)
    fake_client = FakeDockerClient(None)
    monkeypatch.setattr(container, "docker_client", fake_client)

    assert container.is_running() is False


def test_ip_address_returns_container_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = apollo_container(monkeypatch)

    assert container.ip_address == "172.17.0.2"


def test_ip_address_falls_back_to_localhost_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker_container = FakeDockerContainer(
        attrs={
            "NetworkSettings": {
                "Networks": {
                    "bridge": {
                        "IPAddress": "",
                    },
                },
            },
        }
    )
    container = apollo_container(monkeypatch, docker_container)

    assert container.ip_address == "localhost"


def test_exec_command_sources_apollo_environment_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker_container = FakeDockerContainer(output=b"ok")
    container = apollo_container(monkeypatch, docker_container)
    monkeypatch.setenv("USER", "alice")

    output = container.exec_command("echo ok")

    assert output == "ok"
    assert docker_container.exec_calls == [
        ExecRunCall(
            command='bash -c "source /apollo/scripts/apollo_base.sh; echo ok"',
            user="alice",
            workdir="/apollo",
            environment={"HOME": "/home/alice"},
            stream=False,
            detach=False,
        )
    ]


def test_exec_command_honors_explicit_user_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker_container = FakeDockerContainer(output=b"ok")
    container = apollo_container(monkeypatch, docker_container)
    monkeypatch.setenv("USER", "alice")

    output = container.exec_command("echo ok", user="root")

    assert output == "ok"
    assert docker_container.exec_calls == [
        ExecRunCall(
            command='bash -c "source /apollo/scripts/apollo_base.sh; echo ok"',
            user="root",
            workdir="/apollo",
            environment={"HOME": "/home/root"},
            stream=False,
            detach=False,
        )
    ]


def test_exec_command_can_skip_apollo_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker_container = FakeDockerContainer(output=b"/apollo\n")
    container = apollo_container(monkeypatch, docker_container)
    monkeypatch.setenv("USER", "alice")

    output = container.exec_command("pwd", use_apollo_env=False)

    assert output == "/apollo\n"
    assert docker_container.exec_calls[0].command == "pwd"


def test_exec_command_returns_empty_string_for_detached_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker_container = FakeDockerContainer(output=b"ignored")
    container = apollo_container(monkeypatch, docker_container)
    monkeypatch.setenv("USER", "alice")

    output = container.exec_command("sleep 10", detach=True)

    assert output == ""
    assert docker_container.exec_calls[0].detach is True


def test_exec_command_collects_streamed_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker_container = FakeDockerContainer(stream_output=[b"one", b"two"])
    container = apollo_container(monkeypatch, docker_container)
    monkeypatch.setenv("USER", "alice")

    output = container.exec_command("echo stream", stream=True)

    assert output == "onetwo"
    assert docker_container.exec_calls[0].stream is True


def test_reset_kills_processes_except_pid_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker_container = FakeDockerContainer()
    container = apollo_container(monkeypatch, docker_container)
    monkeypatch.setenv("USER", "alice")

    container.reset()

    command = docker_container.exec_calls[0].command
    assert command.startswith(
        'bash -c "source /apollo/scripts/apollo_base.sh; '
    )
    assert "kill -9 $(ps -eo pid= | awk '$1 != 1')" in command


def test_check_file_exists_returns_true_for_existing_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker_container = FakeDockerContainer(output=b"exists\n")
    container = apollo_container(monkeypatch, docker_container)
    monkeypatch.setenv("USER", "alice")

    assert container.check_file_exists("/apollo/file.txt") is True


def test_check_file_exists_returns_false_for_missing_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker_container = FakeDockerContainer(output=b"not exists\n")
    container = apollo_container(monkeypatch, docker_container)
    monkeypatch.setenv("USER", "alice")

    assert container.check_file_exists("/apollo/file.txt") is False


def test_remove_file_runs_rm_command(monkeypatch: pytest.MonkeyPatch) -> None:
    docker_container = FakeDockerContainer()
    container = apollo_container(monkeypatch, docker_container)
    monkeypatch.setenv("USER", "alice")

    container.remove_file("/apollo/file.txt")

    assert "rm -f /apollo/file.txt" in docker_container.exec_calls[0].command


def test_remove_directory_runs_rm_command_without_streaming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    docker_container = FakeDockerContainer()
    container = apollo_container(monkeypatch, docker_container)
    monkeypatch.setenv("USER", "alice")

    container.remove_directory("/apollo/tmp")

    assert "rm -rf /apollo/tmp" in docker_container.exec_calls[0].command
    assert docker_container.exec_calls[0].stream is False


def test_copy_file_to_container_runs_docker_cp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    container = apollo_container(monkeypatch)
    monkeypatch.setattr(
        "baidu_apollo_sdk.apollo_container.subprocess.run", fake_run
    )

    container.copy_file_to_container("/tmp/local.txt", "/apollo/remote.txt")

    assert calls == [
        [
            "docker",
            "cp",
            "/tmp/local.txt",
            "apollo_dev_yuqi:/apollo/remote.txt",
        ]
    ]


def test_copy_file_from_container_runs_docker_cp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        cmd: list[str],
        capture_output: bool,
        text: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    container = apollo_container(monkeypatch)
    monkeypatch.setattr(
        "baidu_apollo_sdk.apollo_container.subprocess.run", fake_run
    )

    container.copy_file_from_container("/apollo/remote.txt", "/tmp/local.txt")

    assert calls == [
        [
            "docker",
            "cp",
            "apollo_dev_yuqi:/apollo/remote.txt",
            "/tmp/local.txt",
        ]
    ]


def test_start_runs_packaged_dev_start_script(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script_path = tmp_path / "v11_dev_start.sh"
    script_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    docker_container = FakeDockerContainer(status="running")
    container = apollo_container(monkeypatch, docker_container)
    calls: list[tuple[str, dict[str, str], bool, bool]] = []

    def fake_run(
        cmd: str,
        env: dict[str, str],
        shell: bool,
        capture_output: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        calls.append((cmd, env, shell, capture_output))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(
        "baidu_apollo_sdk.apollo_container.files",
        lambda package: tmp_path,
    )
    monkeypatch.setattr(
        "baidu_apollo_sdk.apollo_container.subprocess.run", fake_run
    )
    monkeypatch.setenv("USER", "alice")

    container.start()

    assert calls == [
        (
            f"bash {script_path} -y -l --name yuqi",
            {
                "CURR_DIR": "/apollo/root/docker/scripts",
                "USER": "alice",
            },
            True,
            True,
        )
    ]


def test_start_selects_v7_dev_start_script(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script_path = tmp_path / "v7_dev_start.sh"
    script_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    container = apollo_container(monkeypatch, version=7)
    calls: list[str] = []

    def fake_run(
        cmd: str,
        env: dict[str, str],
        shell: bool,
        capture_output: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(
        "baidu_apollo_sdk.apollo_container.files",
        lambda package: tmp_path,
    )
    monkeypatch.setattr(
        "baidu_apollo_sdk.apollo_container.subprocess.run", fake_run
    )
    monkeypatch.setenv("USER", "alice")

    container.start()

    assert calls == [f"bash {script_path} -y -l --name yuqi"]


def test_start_raises_when_packaged_script_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    container = apollo_container(monkeypatch)
    monkeypatch.setattr(
        "baidu_apollo_sdk.apollo_container.files",
        lambda package: tmp_path,
    )

    with pytest.raises(RuntimeError, match="Script not found"):
        container.start()


def test_start_raises_when_user_is_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script_path = tmp_path / "v11_dev_start.sh"
    script_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    container = apollo_container(monkeypatch)
    monkeypatch.setattr(
        "baidu_apollo_sdk.apollo_container.files",
        lambda package: tmp_path,
    )
    monkeypatch.delenv("USER", raising=False)

    with pytest.raises(
        RuntimeError, match="USER environment variable is not set"
    ):
        container.start()


def test_start_raises_when_container_does_not_start(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    script_path = tmp_path / "v11_dev_start.sh"
    script_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    docker_container = FakeDockerContainer(status="exited")
    container = apollo_container(monkeypatch, docker_container)

    def fake_run(
        cmd: str,
        env: dict[str, str],
        shell: bool,
        capture_output: bool,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(
        "baidu_apollo_sdk.apollo_container.files",
        lambda package: tmp_path,
    )
    monkeypatch.setattr(
        "baidu_apollo_sdk.apollo_container.subprocess.run", fake_run
    )
    monkeypatch.setenv("USER", "alice")

    with pytest.raises(RuntimeError, match="Failed to start container"):
        container.start()


@pytest.mark.integration
def test_container_reports_running_status_for_available_container(
    apollo_test_container: ApolloContainer,
) -> None:
    assert apollo_test_container.container_name.startswith(
        ApolloContainer.DEV_CONTAINER_PREFIX
    )
    assert apollo_test_container.container_name != "apollo_dev_yuqi"
    assert apollo_test_container.is_running() is True
    assert apollo_test_container.ip_address


@pytest.mark.integration
def test_container_executes_command_in_available_container(
    apollo_test_container: ApolloContainer,
) -> None:
    output = apollo_test_container.exec_command("pwd", use_apollo_env=False)

    assert output.strip() == "/apollo"


@pytest.mark.integration
def test_container_checks_file_existence_in_available_container(
    apollo_test_container: ApolloContainer,
) -> None:
    assert (
        apollo_test_container.check_file_exists(
            "/apollo/scripts/apollo_base.sh"
        )
        is True
    )
    assert (
        apollo_test_container.check_file_exists(
            "/apollo/this_file_should_not_exist_in_tests"
        )
        is False
    )


@pytest.mark.integration
def test_container_copies_file_to_and_from_available_container(
    apollo_test_container: ApolloContainer,
    tmp_path: Path,
) -> None:
    token = uuid.uuid4().hex
    local_source = tmp_path / "source.txt"
    local_destination = tmp_path / "destination.txt"
    container_path = f"/tmp/baidu_apollo_sdk_container_test_{token}.txt"
    local_source.write_text(f"container-copy-{token}", encoding="utf-8")

    try:
        apollo_test_container.copy_file_to_container(
            str(local_source), container_path
        )
        assert apollo_test_container.check_file_exists(container_path) is True

        apollo_test_container.copy_file_from_container(
            container_path,
            str(local_destination),
        )

        assert local_destination.read_text(encoding="utf-8") == (
            f"container-copy-{token}"
        )
    finally:
        apollo_test_container.remove_file(container_path)
