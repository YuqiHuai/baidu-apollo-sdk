"""High-level runtime operations for an Apollo container."""

import string
from time import perf_counter, sleep

import nanoid

from baidu_apollo_sdk.apollo_container import ApolloContainer


class ApolloRuntime:
    """Runs Apollo build, startup, map, and recorder commands in a container.

    Attributes:
        container: Apollo container wrapper used to execute runtime commands.
    """

    def __init__(self, container: ApolloContainer):
        """Initialize the runtime wrapper.

        Args:
            container: Running or startable Apollo container.
        """
        self.container = container

    def build(self, stream: bool = False) -> None:
        """Build Apollo inside the container.

        Args:
            stream: Whether to stream the output of the build command. Default
                is False.

        Raises:
            RuntimeError: If the container is not running before build.
        """
        if not self.container.is_running():
            raise RuntimeError("Container must be running before build")

        console_out = self.container.exec_command(
            "bash apollo.sh build", stream=stream
        )
        # check if "Done building apollo. Enjoy!" is in console_out
        if "Done building apollo. Enjoy!" not in console_out:
            raise RuntimeError("Build failed. Console output:\n" + console_out)

    def bootstrap(self, stream: bool = False) -> None:
        """Start Apollo's standard bootstrap services in the container.

        Args:
            stream: Whether to stream the output of the bootstrap command.
                    Default is False.
        """
        self.container.exec_command(
            "bash scripts/bootstrap.sh start_plus", stream=stream
        )

    def start_dreamview(self, stream: bool = False) -> None:
        """Start Dreamview in the container.

        Args:
            stream: Whether to stream command output.
        """
        self.container.exec_command(
            "bash scripts/bootstrap.sh start_dreamview", stream=stream
        )

    def start_bridge(self) -> None:
        """Start cyber-bridge in detached mode inside the container."""
        self.container.exec_command("bash scripts/bridge.sh", detach=True)

    def ensure_container(self, restart: bool = False) -> None:
        """Ensure the container is running, and start it if not.

        Args:
            restart: If True, restart the container if it is already running.
                Default is False.
        """
        if not self.container.is_running() or restart:
            self.container.start()

    def start_recorder(
        self, record_name: str, segment_duration: int = 3600
    ) -> None:
        """Start recording cyber data in the container.

        Args:
            record_name: The name of the record file.
            segment_duration: The duration of each segment in seconds.
                Default is 3600 seconds (1 hour).
        """
        recorder_bin = (
            "/apollo/bazel-bin/cyber/tools/cyber_recorder/cyber_recorder"
        )
        cmd = (
            f"{recorder_bin} record -a -o /apollo/data/bag/{record_name} "
            f"-i {segment_duration}"
        )
        self.container.exec_command(cmd, detach=True)

    def stop_recorder(self) -> None:
        """Stop all running recorders in the container."""
        self.container.exec_command(
            "bash -c 'pgrep -f cyber_recorder | xargs -r kill -2'"
        )

    def list_cyber_nodes(self) -> list[str]:
        """List all cyber nodes in the container.

        Returns:
            A list of cyber node names.
        """
        cyber_node_bin = "/apollo/bazel-bin/cyber/tools/cyber_node/cyber_node"
        output = self.container.exec_command(f"{cyber_node_bin} list")
        lines = output.strip().split("\n")
        nodes = []
        skipping = True
        for line in lines:
            if line.startswith("Number of active nodes:"):
                skipping = False
                continue
            if skipping:
                continue
            if line.strip() == "":
                continue
            nodes.append(line.strip())
        return nodes

    def wait_for_node(
        self,
        node_name: str,
        poll_interval: float = 1.0,
        timeout: float | None = None,
    ) -> None:
        """Wait for a specific cyber node to be running in the container.

        Args:
            node_name: The name of the cyber node to wait for.
            poll_interval: The interval in seconds between checks.
                Default is 1.0 second.
            timeout: The maximum time to wait in seconds. If None, wait
                indefinitely. Default is None.

        Raises:
            TimeoutError: If the specified node does not start within the
                timeout period.
        """

        start_time = perf_counter()
        while True:
            nodes = self.list_cyber_nodes()
            if node_name in nodes:
                break
            sleep(poll_interval)
            if timeout is not None and (perf_counter() - start_time) > timeout:
                raise TimeoutError(
                    "Timeout while waiting for node "
                    f"'{node_name}' to be running."
                )

    def list_hd_maps(self) -> list[str]:
        """List all HD maps available in the container.

        Returns:
            A list of HD map names.
        """
        output = self.container.exec_command(
            "find /apollo/modules/map/data -maxdepth 1"
            " -mindepth 1 -type d -printf '%f\\n'",
            use_apollo_env=False,
        )
        lines = output.strip().split("\n")
        maps = []
        for line in lines:
            if line.strip() == "":
                continue
            maps.append(line.strip())
        return maps

    def install_hd_map(
        self, hd_map_path: str, map_name: str | None = None
    ) -> str:
        """Install a specific HD map in the container.

        Args:
            hd_map_path: The path to the HD map to load.
            map_name: The name to assign to the installed HD map. If None, a
                random name will be generated. Default is None.
        Returns:
            The name of the installed HD map.
        Raises:
            ValueError: If the specified map name already exists in the
                container.
            RuntimeError: If the routing/sim map cannot be created for the HD
                map.
        """
        maps = self.list_hd_maps()
        if map_name == "":
            map_name = None

        if map_name is not None and map_name in maps:
            raise ValueError(
                f"Map name '{map_name}' already exists in the container. "
                f"Available maps: {maps}"
            )

        if map_name is None:
            while True:
                map_name = nanoid.generate(string.ascii_lowercase, 16)
                if map_name not in maps:
                    break

        # create directory under /apollo/modules/map/data with the map name
        self.container.exec_command(
            f"mkdir -p /apollo/modules/map/data/{map_name}",
            use_apollo_env=False,
        )
        # copy the HD map file to the container
        self.container.copy_file_to_container(
            hd_map_path, f"/apollo/modules/map/data/{map_name}/"
        )

        # run command to generate routing map and sim map
        map_dir = f"/apollo/modules/map/data/{map_name}"
        self.container.exec_command(
            "bash /apollo/scripts/generate_routing_topo_graph.sh "
            f"--map_dir {map_dir}",
            use_apollo_env=False,
        )
        self.container.exec_command(
            f"bazel-bin/modules/map/tools/sim_map_generator "
            f"--map_dir={map_dir} --output_dir={map_dir}",
            use_apollo_env=True,
        )

        routing_map_created = self.container.check_file_exists(
            f"/apollo/modules/map/data/{map_name}/routing_map.bin"
        )
        sim_map_created = self.container.check_file_exists(
            f"/apollo/modules/map/data/{map_name}/sim_map.bin"
        )

        if not routing_map_created:
            raise RuntimeError(
                f"Failed to create routing map for HD map '{map_name}'"
            )
        if not sim_map_created:
            raise RuntimeError(
                f"Failed to create sim map for HD map '{map_name}'"
            )

        return map_name

    def set_hd_map(self, map_id: str) -> None:
        """Set the current HD map in the container.

        Args:
            map_id: The ID of the HD map to set as current.
        Raises:
            ValueError: If the specified map ID is not valid.
        """
        # check if map_id is valid
        maps = self.list_hd_maps()
        if map_id not in maps:
            raise ValueError(
                f"Map ID '{map_id}' is not valid. Available maps: {maps}"
            )

        configuration_string = f"--map_dir=/apollo/modules/map/data/{map_id}"
        # Write configuration to Apollo's shared global flag file.
        self.container.exec_command(
            f"bash -c \"echo '{configuration_string}'"
            ' >> /apollo/modules/common/data/global_flagfile.txt"',
            use_apollo_env=False,
            stream=True,
        )
