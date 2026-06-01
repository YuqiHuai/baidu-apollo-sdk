from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import pytest

from baidu_apollo_sdk.apollo_container import ApolloContainer
from baidu_apollo_sdk.apollo_runtime import ApolloRuntime


@dataclass
class CommandCall:
    command: str
    detach: bool = False
    stream: bool = False
    use_apollo_env: bool = True


class FakeContainer:
    def __init__(self, version: int = 11) -> None:
        self.version = version
        self.running = True
        self.started = False
        self.commands: list[CommandCall] = []
        self.copied_files: list[tuple[str, str]] = []
        self.existing_files: set[str] = set()
        self.command_outputs: dict[str, str] = {}

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
    ) -> str:
        self.commands.append(
            CommandCall(
                command=command,
                detach=detach,
                stream=stream,
                use_apollo_env=use_apollo_env,
            )
        )
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


def test_ensure_container_starts_when_stopped_or_restart_requested() -> None:
    stopped_container = FakeContainer()
    stopped_container.running = False
    runtime_for(stopped_container).ensure_container()
    assert stopped_container.started is True

    running_container = FakeContainer()
    runtime_for(running_container).ensure_container(restart=True)
    assert running_container.started is True


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


def test_set_hd_map_validates_map_and_writes_global_flag() -> None:
    container = FakeContainer()
    container.command_outputs[
        "find /apollo/modules/map/data -maxdepth 1"
        " -mindepth 1 -type d -printf '%f\\n'"
    ] = "borregas_ave\n"

    runtime_for(container).set_hd_map("borregas_ave")

    assert container.commands[-1] == CommandCall(
        "bash -c \"echo '--map_dir=/apollo/modules/map/data/borregas_ave'"
        ' >> /apollo/modules/common/data/global_flagfile.txt"',
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
