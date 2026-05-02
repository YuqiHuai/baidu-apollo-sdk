from time import perf_counter, sleep

from apollo_instance.apollo_container import ApolloContainer


class ApolloRuntime:
    def __init__(self, container: ApolloContainer):
        self.container = container

    def build(self, stream: bool = False):
        if not self.container.is_running():
            raise RuntimeError("Container must be running before build")

        self.container.exec_command("bash apollo.sh build", stream=stream)

    def bootstrap(self, stream: bool = False):
        """
        Bootstrap the Apollo runtime environment by running the bootstrap script
        inside the container.
        """
        self.container.exec_command(
            "bash scripts/bootstrap.sh start_plus", stream=stream
        )

    def ensure_container(self, restart=False):
        """Ensure the container is running, and start it if not.

        Args:
            restart: If True, restart the container if it is already running.
                Default is False.
        """
        if not self.container.is_running() or restart:
            self.container.start()

    def start_recorder(self, record_name: str, segment_duration: int = 3600):
        """Start recording cyber data in the container.

        Args:
            record_name: The name of the record file.
            segment_duration: The duration of each segment in seconds.
                Default is 3600 seconds (1 hour).
        """
        recorder_bin = "/apollo/bazel-bin/cyber/tools/cyber_recorder/cyber_recorder"
        cmd = (
            f"{recorder_bin} record -a -o /apollo/data/bag/{record_name} "
            f"-i {segment_duration}"
        )
        self.container.exec_command(cmd, detach=True)

    def stop_recorder(self):
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
                    f"Timeout while waiting for node '{node_name}' to be running."
                )
