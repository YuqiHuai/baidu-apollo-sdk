import os
import shlex
import subprocess
import time

import docker
from loguru import logger


class Container:
    def __init__(self, name: str):
        self.name = name
        self.docker_client = docker.from_env()

    def start(self) -> bool:
        """
        Start the container.

        Args:
            name: The name of the container to start.

        Returns:
            True if the container is started successfully, False otherwise.

        Raises:
            RuntimeError: If the container fails to start.
        """
        logger.info(f"{self.name}: Starting container")
        cmd = (
            "bash /home/yuqi/ResearchWorkspace/ICSE_2027/"
            "apollo-v11.0.0/docker/scripts/dev_start.sh -l"
        )
        process = subprocess.Popen(
            shlex.split(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        _, stderr = process.communicate()
        if process.returncode != 0:
            raise RuntimeError(f"Failed to start container: {stderr.decode('utf-8')}")
        return True

    def is_running(self) -> bool:
        """Check if the container is running.

        Returns:
            True if the container is running, False otherwise.
        """

        try:
            container = self.docker_client.containers.get(self.name)
            return container.status == "running"
        except docker.errors.NotFound:
            return False

    @property
    def ip_address(self) -> str:
        """Get the IP address of the container.

        Returns:
            The IP address of the container, or "localhost" if it cannot be determined.
        """

        container = self.docker_client.containers.get(self.name)
        networks = container.attrs["NetworkSettings"]["Networks"]
        ip_address = ""
        if networks and len(networks) > 0:
            ip_address = list(networks.values())[0]["IPAddress"]
        ip_address = ip_address.strip()
        if ip_address == "":
            return "localhost"
        return ip_address

    def exec_command(
        self, command: str, detach: bool = False, stream: bool = False
    ) -> str:
        """Execute a command in the container.

        Args:
            command: The command to execute.
            detach: Whether to run the command in detached mode. Default is False.
            stream: Whether to stream the output of the command. Default is False.

        Returns:
            The output of the command if detach is False, otherwise an empty string.
        """
        logger.info(f"{self.name}: Executing command: {command}")
        container = self.docker_client.containers.get(self.name)
        user = os.environ.get("USER")
        assert user is not None, "USER environment variable is not set"
        exec_stream = container.exec_run(
            'bash -c "source /apollo/scripts/apollo_base.sh; ' + command + '"',
            user=user,
            workdir="/apollo",
            environment={
                "HOME": "/home/" + user,
            },
            stream=stream,
            detach=detach,
        )

        if detach:
            return ""
        if not stream:
            return exec_stream.output.decode("utf-8", errors="ignore")

        output = []

        for chunk in exec_stream.output:
            text = chunk.decode("utf-8", errors="ignore")
            output.append(text)

        return "".join(output)

    def reset(self) -> None:
        """Reset the container by killing all processes except PID 1."""
        logger.info(f"{self.name}: Resetting container.")
        self.exec_command("bash -c \"kill -9 $(ps -eo pid= | awk '$1 != 1')\"")

    def start_recorder(self, record_name: str, segment_duration: int = 3600) -> None:
        """Start recording cyber data in the container.

        Args:
            record_name: The name of the record file.
            segment_duration: The duration of each segment in seconds.
                Default is 3600 seconds (1 hour).
        """
        logger.info(f"{self.name}: Starting recorder: {record_name}.")
        recorder_bin = "/apollo/bazel-bin/cyber/tools/cyber_recorder/cyber_recorder"
        record_command = (
            f"{recorder_bin} record -a -o /apollo/data/bag/{record_name} "
            f"-i {segment_duration}"
        )
        self.exec_command(record_command, detach=True)

    def stop_recorder(self) -> None:
        """Stop all running recorders in the container."""
        logger.info(f"{self.name}: Stopping recorder.")
        self.exec_command("bash -c 'pgrep -f cyber_recorder | xargs -r kill -2'")

    def list_cyber_nodes(self) -> list[str]:
        """List all cyber nodes in the container.

        Returns:
            A list of cyber node names.
        """
        cyber_node_bin = "/apollo/bazel-bin/cyber/tools/cyber_node/cyber_node"
        output = self.exec_command(f"{cyber_node_bin} list")
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

        start_time = time.perf_counter()
        while True:
            nodes = self.list_cyber_nodes()
            if node_name in nodes:
                break
            time.sleep(poll_interval)
            if timeout is not None and (time.perf_counter() - start_time) > timeout:
                raise TimeoutError(
                    f"Timeout while waiting for node '{node_name}' to be running."
                )
