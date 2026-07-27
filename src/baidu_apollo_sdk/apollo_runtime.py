"""High-level runtime operations for an Apollo container."""

import string
from time import perf_counter, sleep

import nanoid

from baidu_apollo_sdk.apollo_container import ApolloContainer
from baidu_apollo_sdk.logging import container_log_prefix, get_logger

logger = get_logger()

# Stable path to the bazel-built runfiles tree for the v11 service_bridge
# py_binary target. Resolving imports (cyber bindings + generated external
# command protobufs) through this tree avoids depending on the bazel cache's
# hash-named output directories, which differ per build.
SERVICE_BRIDGE_RUNFILES_PATH = (
    "/apollo/bazel-bin/modules/contrib/cyber_bridge/"
    "_install_service_bridge.runfiles/apollo"
)

# The cyber_bridge binary itself, as it appears in the container's process
# table. `scripts/bridge.sh` runs it in the foreground rather than exec'ing
# it, so matching this path identifies the bridge process without also
# matching the wrapper shell (which exits on its own once the binary does).
BRIDGE_BINARY = "/apollo/bazel-bin/modules/contrib/cyber_bridge/cyber_bridge"


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

        logger.info("{} build", container_log_prefix(self.container))
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
        logger.info("{} bootstrap", container_log_prefix(self.container))
        if self.container.version == 7:
            self.start_dreamview(stream=stream)
        else:
            self.start_dreamview_plus(stream=stream)

    def start_dreamview(self, stream: bool = False) -> None:
        """Start Dreamview in the container.

        Runs as root: Apollo's own module processes (dreamview, monitor,
        mainboard) run as root inside the container, and CyberRT's
        shared-memory transport is permission-sensitive across UIDs. A
        Dreamview started as a different user comes up and serves its own
        frontend fine, but SimControl (embedded in the same process) then
        publishes on channels a root-run reader (or another root-run Apollo
        module) cannot see -- e.g. every `cyber_channel echo` in this SDK --
        which looks exactly like SimControl never placing the vehicle at all.

        Args:
            stream: Whether to stream command output.
        """
        logger.info("{} start dreamview", container_log_prefix(self.container))
        self.container.exec_command(
            "bash scripts/bootstrap.sh start", stream=stream, user="root"
        )

    def start_dreamview_plus(self, stream: bool = False) -> None:
        """Start Dreamview Plus in the container.

        Runs as root -- see `start_dreamview`.

        Args:
            stream: Whether to stream command output.
        """
        logger.info(
            "{} start dreamview plus", container_log_prefix(self.container)
        )
        self.container.exec_command(
            "bash scripts/bootstrap.sh start_plus", stream=stream, user="root"
        )

    def bridge_process_users(self) -> list[str]:
        """Return the owning user of every running cyber_bridge process."""
        output = self.container.exec_command(
            "ps -eo user:32,args --no-headers", use_apollo_env=False
        )
        users = []
        for line in output.strip().splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2 and parts[1].startswith(BRIDGE_BINARY):
                users.append(parts[0])
        return users

    def start_bridge(self) -> None:
        """Start cyber-bridge in detached mode inside the container, as root.

        cyber_bridge has to run as root. It subscribes to channels published
        by Apollo's own module processes (planning, routing, and
        dreamview/sim_control), every one of which runs as root, and
        CyberRT's shared-memory transport is permission-sensitive across
        UIDs -- see `ApolloContainer.exec_command`'s `user` argument. A
        non-root bridge connects, accepts subscriptions, and reports no
        error while delivering *zero* messages, which downstream looks
        exactly like an ego vehicle that never moved and a behavior that
        never activated.

        Readiness is therefore decided by the bridge process's owner, not
        by whether a node named "bridge" is registered: a non-root bridge
        registers that node just the same, so reusing it on that basis is
        what silently breaks. Such a bridge is killed and replaced.
        """
        users = self.bridge_process_users()
        if users and all(user == "root" for user in users):
            logger.info(
                "{} bridge running", container_log_prefix(self.container)
            )
            return
        if users:
            logger.warning(
                "{} replacing cyber_bridge owned by {} -- a non-root bridge "
                "silently receives no messages",
                container_log_prefix(self.container),
                ", ".join(sorted(set(users))),
            )
            self.container.exec_command(
                f"pkill -f {BRIDGE_BINARY}", user="root", use_apollo_env=False
            )
        logger.info("{} start bridge", container_log_prefix(self.container))
        self.container.exec_command(
            "bash scripts/bridge.sh", detach=True, user="root"
        )

    def start_service_bridge(
        self, host: str = "0.0.0.0", port: int = 9091
    ) -> None:
        """Start the Apollo v11 external-command HTTP service bridge.

        Runs ``service_bridge.py`` in detached mode, exposing the
        ``/action``, ``/lane_follow``, and ``/valet_parking`` HTTP
        endpoints used by ``CommandSender``. Binds ``0.0.0.0`` by default
        so the bridge is reachable via ``ApolloContainer.ip_address`` from
        outside the container, not just from within it.

        Args:
            host: Interface to bind. Defaults to all interfaces.
            port: Port to listen on.

        Raises:
            RuntimeError: If the container is not running Apollo v11.
        """
        if self.container.version != 11:
            raise RuntimeError(
                "service bridge is only available for Apollo v11"
            )
        nodes = self.list_cyber_nodes()
        if "service_bridge" in nodes:
            logger.info(
                "{} service bridge running",
                container_log_prefix(self.container),
            )
            return
        logger.info(
            "{} start service bridge", container_log_prefix(self.container)
        )
        command = (
            f"export PYTHONPATH={SERVICE_BRIDGE_RUNFILES_PATH}:$PYTHONPATH "
            "&& python3 modules/contrib/cyber_bridge/service_bridge.py "
            f"--host {host} --port {port}"
        )
        self.container.exec_command(command, detach=True)

    def ensure_container(
        self, restart: bool = False, verbose: bool = False
    ) -> None:
        """Ensure the container is running, and start it if not.

        Args:
            restart: If True, restart the container if it is already running.
                Default is False.
            verbose: If True, stream the startup script output.
                Default is False.
        """
        if not self.container.is_running() or restart:
            logger.info(
                "{} ensure container", container_log_prefix(self.container)
            )
            self.container.start(verbose=verbose)

    def start_recorder(
        self, record_name: str, segment_duration: int = 3600
    ) -> None:
        """Start recording cyber data in the container.

        Runs as root: Apollo's own module processes (dreamview, monitor,
        mainboard) run as root inside the container, and CyberRT's
        shared-memory transport is permission-sensitive across UIDs. A
        recorder started as a different user discovers channels fine but
        silently fails to receive most published messages.

        Args:
            record_name: The name of the record file.
            segment_duration: The duration of each segment in seconds.
                Default is 3600 seconds (1 hour).
        """
        recorder_bin = (
            "/apollo/bazel-bin/cyber/tools/cyber_recorder/cyber_recorder"
        )
        filename = f"/apollo/data/bag/{record_name}"
        cmd = (
            f"{recorder_bin} record -a -o /apollo/data/bag/{record_name} "
            f"-i {segment_duration}"
        )
        logger.info(
            "{} start recorder {}",
            container_log_prefix(self.container),
            record_name,
        )
        self.container.exec_command(cmd, detach=True, user="root")
        return f"{filename}.00000"

    def stop_recorder(
        self, timeout: float = 10.0, poll_interval: float = 0.2
    ) -> None:
        """Stop all running recorders and wait for them to exit.

        Runs as root, matching ``start_recorder``: the recorder process is
        owned by root, and only root can signal it. Blocks until the
        recorder process has actually exited (not just been signalled), so
        the record file is fully flushed and finalized by the time this
        returns.

        Args:
            timeout: Maximum time to wait for the recorder to exit.
            poll_interval: Time between liveness checks.

        Raises:
            TimeoutError: If the recorder is still running after `timeout`.
        """
        logger.info("{} stop recorders", container_log_prefix(self.container))
        # Match on process name (-x), not full command line (-f): a -f
        # pattern self-matches the invoking "bash -c '...cyber_recorder...'"
        # wrapper, since that wrapper's own command line also contains the
        # search string, which would make the liveness check below always
        # see something "running" and never return.
        self.container.exec_command(
            "bash -c 'pgrep -x cyber_recorder | xargs -r kill -2'",
            user="root",
        )
        start_time = perf_counter()
        while self._recorder_running():
            sleep(poll_interval)
            if perf_counter() - start_time > timeout:
                raise TimeoutError(
                    "Timeout while waiting for cyber_recorder to stop"
                )

    def _recorder_running(self) -> bool:
        output = self.container.exec_command(
            "bash -c 'pgrep -x cyber_recorder || true'",
            use_apollo_env=False,
            user="root",
        )
        return bool(output.strip())

    def list_cyber_nodes(self) -> list[str]:
        """List all cyber nodes in the container.

        Returns:
            A list of cyber node names.
        """
        cyber_node_bin = "/apollo/bazel-bin/cyber/tools/cyber_node/cyber_node"
        logger.info("{} list cyber nodes", container_log_prefix(self.container))
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
        logger.info(
            "{} wait node {}",
            container_log_prefix(self.container),
            node_name,
        )
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
        logger.info("{} list maps", container_log_prefix(self.container))
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
        logger.info(
            "{} install map {}",
            container_log_prefix(self.container),
            map_name or hd_map_path,
        )
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

        logger.info(
            "{} installed map {}",
            container_log_prefix(self.container),
            map_name,
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
        logger.info(
            "{} set map {}", container_log_prefix(self.container), map_id
        )
        maps = self.list_hd_maps()
        if map_id not in maps:
            raise ValueError(
                f"Map ID '{map_id}' is not valid. Available maps: {maps}"
            )

        configuration_string = f"--map_dir=/apollo/modules/map/data/{map_id}"
        flag_file = "/apollo/modules/common/data/global_flagfile.txt"
        # Update the current map selection instead of accumulating new flags.
        self.container.exec_command(
            'bash -c "'
            f"if grep -q '^--map_dir=' {flag_file}; then "
            f"sed -i 's|^--map_dir=.*$|{configuration_string}|' {flag_file}; "
            "else "
            f"echo '{configuration_string}' >> {flag_file}; "
            'fi"',
            use_apollo_env=False,
            stream=True,
        )
