import os
import subprocess
from importlib.resources import files
from pathlib import Path
from typing import cast

import docker
from loguru import logger


class ApolloContainer:
    DEV_CONTAINER_PREFIX = "apollo_dev_"

    def __init__(self, name: str, apollo_path: str):
        self.name = name
        self.apollo_path = apollo_path
        self.docker_client = docker.from_env()

    def start(self, verbose: bool = False) -> bool:
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
        script_path = files("apollo_instance.scripts") / "dev_start.sh"
        if not script_path.exists():
            raise RuntimeError(f"Script not found: {script_path}")

        apollo_docker_scripts_dir = Path(self.apollo_path, "docker", "scripts")
        cmd = f"bash {script_path} -y -l --name {self.name}"
        subprocess.run(
            cmd,
            env={
                "CURR_DIR": apollo_docker_scripts_dir,
                "USER": os.environ.get("USER"),
            },
            shell=True,
            capture_output=not verbose,
        )
        if not self.is_running():
            raise RuntimeError("Failed to start container")

    def is_running(self) -> bool:
        """Check if the container is running.

        Returns:
            True if the container is running, False otherwise.
        """

        try:
            container = self.docker_client.containers.get(self.container_name)
            return bool(container.status == "running")
        except docker.errors.NotFound:
            return False

    @property
    def container_name(self) -> str:
        """Get the container name.

        Returns:
            The container name, which is the prefix plus the name.
        """
        return self.DEV_CONTAINER_PREFIX + self.name

    @property
    def ip_address(self) -> str:
        """Get the IP address of the container.

        Returns:
            The IP address of the container, or "localhost" if it cannot be determined.
        """

        container = self.docker_client.containers.get(self.container_name)
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
        container = self.docker_client.containers.get(self.container_name)
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
            return cast(str, exec_stream.output.decode("utf-8", errors="ignore"))

        output = []

        for chunk in exec_stream.output:
            text = chunk.decode("utf-8", errors="ignore")
            print(text, end="", flush=True)  # 👈 THIS is the key
            output.append(text)

        return "".join(output)

    def reset(self) -> None:
        """Reset the container by killing all processes except PID 1."""
        logger.info(f"{self.name}: Resetting container.")
        self.exec_command("bash -c \"kill -9 $(ps -eo pid= | awk '$1 != 1')\"")
