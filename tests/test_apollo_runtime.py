from __future__ import annotations

import time
from dataclasses import dataclass
from typing import cast
from urllib.request import urlopen

import pytest

from baidu_apollo_sdk.apollo_container import ApolloContainer
from baidu_apollo_sdk.apollo_runtime import (
    SERVICE_BRIDGE_RUNFILES_PATH,
    ApolloRuntime,
)


@dataclass
class CommandCall:
    command: str
    detach: bool = False
    stream: bool = False
    use_apollo_env: bool = True
    user: str | None = None


class FakeContainer:
    def __init__(self, version: int = 11) -> None:
        self.version = version
        self.running = True
        self.started = False
        self.commands: list[CommandCall] = []
        self.copied_files: list[tuple[str, str]] = []
        self.existing_files: set[str] = set()
        self.command_outputs: dict[str, str] = {}
        self.command_output_sequences: dict[str, list[str]] = {}

    def is_running(self) -> bool:
        return self.running

    def start(self, verbose: bool = False) -> None:
        self.started = True
        self.running = True

    def exec_command(
        self,
        command: str,
        detach: bool = False,
        stream: bool = False,
        use_apollo_env: bool = True,
        user: str | None = None,
    ) -> str:
        self.commands.append(
            CommandCall(
                command=command,
                detach=detach,
                stream=stream,
                use_apollo_env=use_apollo_env,
                user=user,
            )
        )
        sequence = self.command_output_sequences.get(command)
        if sequence:
            return sequence.pop(0)
        return self.command_outputs.get(command, "")

    def copy_file_to_container(
        self, local_path: str, container_path: str
    ) -> None:
        self.copied_files.append((local_path, container_path))

    def check_file_exists(self, file_path: str) -> bool:
        return file_path in self.existing_files


def runtime_for(container: FakeContainer) -> ApolloRuntime:
    return ApolloRuntime(cast(ApolloContainer, container))


def test_build_requires_running_container() -> None:
    container = FakeContainer()
    container.running = False

    with pytest.raises(RuntimeError, match="Container must be running"):
        runtime_for(container).build()


def test_build_raises_when_success_marker_is_missing() -> None:
    container = FakeContainer()
    container.command_outputs["bash apollo.sh build"] = "compile failed"

    with pytest.raises(RuntimeError, match="Build failed"):
        runtime_for(container).build()


def test_build_runs_apollo_build_command() -> None:
    container = FakeContainer()
    container.command_outputs["bash apollo.sh build"] = (
        "Done building apollo. Enjoy!"
    )

    runtime_for(container).build(stream=True)

    assert container.commands == [
        CommandCall("bash apollo.sh build", stream=True),
    ]


def test_bootstrap_starts_dreamview_for_v7() -> None:
    container = FakeContainer(version=7)

    runtime_for(container).bootstrap(stream=True)

    assert container.commands == [
        CommandCall("bash scripts/bootstrap.sh start", stream=True),
    ]


def test_bootstrap_starts_dreamview_plus_for_v11() -> None:
    container = FakeContainer(version=11)

    runtime_for(container).bootstrap(stream=True)

    assert container.commands == [
        CommandCall("bash scripts/bootstrap.sh start_plus", stream=True),
    ]


def test_start_recorder_runs_as_root() -> None:
    container = FakeContainer()

    runtime_for(container).start_recorder("run1")

    assert container.commands == [
        CommandCall(
            "/apollo/bazel-bin/cyber/tools/cyber_recorder/cyber_recorder "
            "record -a -o /apollo/data/bag/run1 -i 3600",
            detach=True,
            user="root",
        ),
    ]


def test_start_recorder_honors_custom_segment_duration() -> None:
    container = FakeContainer()

    runtime_for(container).start_recorder("run1", segment_duration=60)

    assert container.commands[-1] == CommandCall(
        "/apollo/bazel-bin/cyber/tools/cyber_recorder/cyber_recorder "
        "record -a -o /apollo/data/bag/run1 -i 60",
        detach=True,
        user="root",
    )


def test_stop_recorder_runs_as_root() -> None:
    container = FakeContainer()

    runtime_for(container).stop_recorder()

    assert container.commands == [
        CommandCall(
            "bash -c 'pgrep -x cyber_recorder | xargs -r kill -2'",
            user="root",
        ),
        CommandCall(
            "bash -c 'pgrep -x cyber_recorder || true'",
            use_apollo_env=False,
            user="root",
        ),
    ]


def test_stop_recorder_waits_for_process_to_exit() -> None:
    container = FakeContainer()
    liveness_command = "bash -c 'pgrep -x cyber_recorder || true'"
    # First poll still finds the process running; second poll finds it gone.
    container.command_output_sequences[liveness_command] = ["12345", ""]

    runtime_for(container).stop_recorder(poll_interval=0.01)

    liveness_checks = [
        c for c in container.commands if c.command == liveness_command
    ]
    assert len(liveness_checks) == 2


def test_stop_recorder_times_out_if_process_never_exits() -> None:
    container = FakeContainer()
    container.command_outputs["bash -c 'pgrep -x cyber_recorder || true'"] = (
        "12345"
    )

    with pytest.raises(TimeoutError, match="Timeout while waiting"):
        runtime_for(container).stop_recorder(timeout=0.05, poll_interval=0.02)


def test_ensure_container_starts_when_stopped_or_restart_requested() -> None:
    stopped_container = FakeContainer()
    stopped_container.running = False
    runtime_for(stopped_container).ensure_container()
    assert stopped_container.started is True

    running_container = FakeContainer()
    runtime_for(running_container).ensure_container(restart=True)
    assert running_container.started is True


CYBER_NODE_LIST_COMMAND = (
    "/apollo/bazel-bin/cyber/tools/cyber_node/cyber_node list"
)


def test_start_service_bridge_rejects_non_v11() -> None:
    container = FakeContainer(version=7)

    with pytest.raises(RuntimeError, match="only available for Apollo v11"):
        runtime_for(container).start_service_bridge()

    assert container.commands == []


def test_start_service_bridge_skips_when_already_running() -> None:
    container = FakeContainer(version=11)
    container.command_outputs[CYBER_NODE_LIST_COMMAND] = (
        "Number of active nodes: 1\n\nservice_bridge\n"
    )

    runtime_for(container).start_service_bridge()

    assert container.commands == [
        CommandCall(CYBER_NODE_LIST_COMMAND),
    ]


def test_start_service_bridge_starts_detached_with_default_host_and_port() -> (
    None
):
    container = FakeContainer(version=11)
    container.command_outputs[CYBER_NODE_LIST_COMMAND] = (
        "Number of active nodes: 0\n\n"
    )

    runtime_for(container).start_service_bridge()

    expected_command = (
        f"export PYTHONPATH={SERVICE_BRIDGE_RUNFILES_PATH}:$PYTHONPATH "
        "&& python3 modules/contrib/cyber_bridge/service_bridge.py "
        "--host 0.0.0.0 --port 9091"
    )
    assert container.commands == [
        CommandCall(CYBER_NODE_LIST_COMMAND),
        CommandCall(expected_command, detach=True),
    ]


def test_start_service_bridge_honors_custom_host_and_port() -> None:
    container = FakeContainer(version=11)
    container.command_outputs[CYBER_NODE_LIST_COMMAND] = (
        "Number of active nodes: 0\n\n"
    )

    runtime_for(container).start_service_bridge(host="127.0.0.1", port=9200)

    expected_command = (
        f"export PYTHONPATH={SERVICE_BRIDGE_RUNFILES_PATH}:$PYTHONPATH "
        "&& python3 modules/contrib/cyber_bridge/service_bridge.py "
        "--host 127.0.0.1 --port 9200"
    )
    assert container.commands[-1] == CommandCall(expected_command, detach=True)


def test_list_cyber_nodes_skips_summary_and_blank_lines() -> None:
    container = FakeContainer()
    container.command_outputs[
        "/apollo/bazel-bin/cyber/tools/cyber_node/cyber_node list"
    ] = "header\nNumber of active nodes: 2\n\n/planning\n /prediction \n"

    assert runtime_for(container).list_cyber_nodes() == [
        "/planning",
        "/prediction",
    ]


def test_list_hd_maps_returns_map_directory_names() -> None:
    container = FakeContainer()
    find_command = (
        "find /apollo/modules/map/data -maxdepth 1"
        " -mindepth 1 -type d -printf '%f\\n'"
    )
    container.command_outputs[find_command] = "\nborregas_ave\nsunnyvale\n\n"

    assert runtime_for(container).list_hd_maps() == [
        "borregas_ave",
        "sunnyvale",
    ]
    assert container.commands == [
        CommandCall(find_command, use_apollo_env=False),
    ]


def test_install_hd_map_rejects_duplicate_map_name() -> None:
    container = FakeContainer()
    container.command_outputs[
        "find /apollo/modules/map/data -maxdepth 1"
        " -mindepth 1 -type d -printf '%f\\n'"
    ] = "borregas_ave\n"

    with pytest.raises(ValueError, match="already exists"):
        runtime_for(container).install_hd_map(
            "/tmp/base_map.txt", "borregas_ave"
        )


def test_install_hd_map_copies_map_and_generates_outputs() -> None:
    container = FakeContainer()
    map_name = "carla_town01"
    map_dir = f"/apollo/modules/map/data/{map_name}"
    container.existing_files = {
        f"{map_dir}/routing_map.bin",
        f"{map_dir}/sim_map.bin",
    }

    result = runtime_for(container).install_hd_map(
        "/tmp/base_map.txt", map_name
    )

    assert result == map_name
    assert container.copied_files == [("/tmp/base_map.txt", f"{map_dir}/")]
    assert container.commands == [
        CommandCall(
            "find /apollo/modules/map/data -maxdepth 1"
            " -mindepth 1 -type d -printf '%f\\n'",
            use_apollo_env=False,
        ),
        CommandCall(f"mkdir -p {map_dir}", use_apollo_env=False),
        CommandCall(
            "bash /apollo/scripts/generate_routing_topo_graph.sh "
            f"--map_dir {map_dir}",
            use_apollo_env=False,
        ),
        CommandCall(
            "bazel-bin/modules/map/tools/sim_map_generator "
            f"--map_dir={map_dir} --output_dir={map_dir}",
        ),
    ]


def test_install_hd_map_generates_name_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = FakeContainer()
    map_name = "generatedmapname"
    map_dir = f"/apollo/modules/map/data/{map_name}"
    container.existing_files = {
        f"{map_dir}/routing_map.bin",
        f"{map_dir}/sim_map.bin",
    }
    monkeypatch.setattr(
        "baidu_apollo_sdk.apollo_runtime.nanoid.generate",
        lambda alphabet, size: map_name,
    )

    assert (
        runtime_for(container).install_hd_map("/tmp/base_map.txt") == map_name
    )


def test_install_hd_map_raises_when_generated_files_are_missing() -> None:
    container = FakeContainer()

    with pytest.raises(RuntimeError, match="Failed to create routing map"):
        runtime_for(container).install_hd_map(
            "/tmp/base_map.txt", "missing_outputs"
        )


def test_set_hd_map_replaces_or_appends_global_flag() -> None:
    container = FakeContainer()
    container.command_outputs[
        "find /apollo/modules/map/data -maxdepth 1"
        " -mindepth 1 -type d -printf '%f\\n'"
    ] = "borregas_ave\n"

    runtime_for(container).set_hd_map("borregas_ave")

    assert container.commands[-1] == CommandCall(
        "bash -c \"if grep -q '^--map_dir=' "
        "/apollo/modules/common/data/global_flagfile.txt; then "
        "sed -i 's|^--map_dir=.*$|"
        "--map_dir=/apollo/modules/map/data/borregas_ave|' "
        "/apollo/modules/common/data/global_flagfile.txt; else "
        "echo '--map_dir=/apollo/modules/map/data/borregas_ave' >> "
        '/apollo/modules/common/data/global_flagfile.txt; fi"',
        stream=True,
        use_apollo_env=False,
    )


def test_set_hd_map_rejects_unknown_map() -> None:
    container = FakeContainer()

    with pytest.raises(ValueError, match="is not valid"):
        runtime_for(container).set_hd_map("unknown_map")


@pytest.mark.integration
def test_runtime_executes_command_in_available_container(
    apollo_test_container: ApolloContainer,
) -> None:
    runtime = ApolloRuntime(apollo_test_container)

    output = runtime.container.exec_command("pwd", use_apollo_env=False)

    assert output.strip() == "/apollo"


@pytest.mark.integration
def test_runtime_records_and_stops_cleanly_in_available_container(
    apollo_test_container: ApolloContainer,
) -> None:
    """Regression test: the recorder must run as root (not the calling
    user) to read Apollo's root-owned CyberRT channels, and stop_recorder
    must wait for the process to actually exit before returning."""
    runtime = ApolloRuntime(apollo_test_container)
    record_name = "integration_test_record"

    runtime.start_recorder(record_name, segment_duration=60)
    time.sleep(1.0)
    runtime.stop_recorder()

    output = runtime.container.exec_command(
        f"ls /apollo/data/bag/{record_name}.00000",
        use_apollo_env=False,
    )
    assert f"{record_name}.00000" in output


@pytest.mark.integration
def test_runtime_lists_hd_maps_in_available_container(
    apollo_test_container: ApolloContainer,
) -> None:
    runtime = ApolloRuntime(apollo_test_container)

    maps = runtime.list_hd_maps()

    assert isinstance(maps, list)
    assert all(map_name for map_name in maps)


@pytest.mark.integration
def test_runtime_lists_cyber_nodes_in_available_container(
    apollo_test_container: ApolloContainer,
) -> None:
    runtime = ApolloRuntime(apollo_test_container)

    nodes = runtime.list_cyber_nodes()

    assert isinstance(nodes, list)
    assert all(
        node_name.strip() == node_name and node_name for node_name in nodes
    )


@pytest.mark.integration
def test_runtime_starts_service_bridge_in_available_container(
    apollo_test_container: ApolloContainer,
) -> None:
    runtime = ApolloRuntime(apollo_test_container)
    if not runtime.container.check_file_exists(
        f"{SERVICE_BRIDGE_RUNFILES_PATH}/cyber/python/cyber_py3/cyber.py"
    ):
        pytest.skip("service_bridge bazel target not built for this container")

    runtime.start_service_bridge()
    runtime.wait_for_node("service_bridge", poll_interval=0.5, timeout=60)

    assert "service_bridge" in runtime.list_cyber_nodes()

    url = f"http://{apollo_test_container.ip_address}:9091/healthz"
    with urlopen(url, timeout=5) as response:  # noqa: S310
        assert response.status == 200


@pytest.mark.integration
def test_runtime_start_service_bridge_is_idempotent(
    apollo_test_container: ApolloContainer,
) -> None:
    runtime = ApolloRuntime(apollo_test_container)
    if not runtime.container.check_file_exists(
        f"{SERVICE_BRIDGE_RUNFILES_PATH}/cyber/python/cyber_py3/cyber.py"
    ):
        pytest.skip("service_bridge bazel target not built for this container")

    runtime.start_service_bridge()
    runtime.wait_for_node("service_bridge", poll_interval=0.5, timeout=60)

    # Calling it again should detect the running node and not error out.
    runtime.start_service_bridge()

    assert "service_bridge" in runtime.list_cyber_nodes()
