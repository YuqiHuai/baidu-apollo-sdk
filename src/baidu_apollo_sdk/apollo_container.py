import os
import shlex
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

    def start(self, verbose: bool = False) -> None:
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
        script_path = files("baidu_apollo_sdk.scripts") / "dev_start.sh"

        if not script_path.is_file():
            raise RuntimeError(f"Script not found: {script_path}")

        apollo_docker_scripts_dir = Path(self.apollo_path, "docker", "scripts")
        cmd = f"bash {script_path} -y -l --name {self.name}"
        current_user = os.environ.get("USER")
        if not current_user:
            raise RuntimeError("USER environment variable is not set")
        subprocess.run(
            cmd,
            env={
                "CURR_DIR": str(apollo_docker_scripts_dir),
                "USER": str(current_user),
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
        self,
        command: str,
        detach: bool = False,
        stream: bool = False,
        use_apollo_env: bool = True,
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

        if use_apollo_env:
            cmd = 'bash -c "source /apollo/scripts/apollo_base.sh; ' + command + '"'
        else:
            cmd = command

        exec_stream = container.exec_run(
            cmd,
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

    def check_file_exists(self, file_path: str) -> bool:
        """Check if a file exists in the container.

        Args:
            file_path: The path to the file to check.
        Returns:
            True if the file exists, False otherwise.
        """
        logger.info(f"{self.name}: Checking if file exists: {file_path}")
        quoted_path = shlex.quote(file_path)
        result = self.exec_command(
            f"bash -c \"test -f {quoted_path} && echo exists || echo 'not exists'\"",
            use_apollo_env=False,
        )
        return result.strip() == "exists"

    def remove_file(self, file_path: str) -> None:
        """Remove a file in the container.

        Args:
            file_path: The path to the file to remove.
        """
        logger.info(f"{self.name}: Removing file: {file_path}")
        self.exec_command(f"rm -f {file_path}")

    def remove_directory(self, dir_path: str) -> None:
        """Remove a directory in the container.

        Args:
            dir_path: The path to the directory to remove.
        """
        logger.info(f"{self.name}: Removing directory: {dir_path}")
        self.exec_command(f"rm -rf {dir_path}", stream=True)

    def copy_file_to_container(self, local_path: str, container_path: str) -> None:
        """Copy a file from the local machine to the container.

        Args:
            local_path: The path to the file on the local machine.
            container_path: The path to the file in the container.
        """
        logger.info(f"{self.name}: Copying file from {local_path} to {container_path}")
        copy_status = subprocess.run(
            [
                "docker",
                "cp",
                local_path,
                f"{self.container_name}:{container_path}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        if copy_status.returncode != 0:
            raise RuntimeError(
                f"Failed to copy file to container: {copy_status.stderr}"
            )

    def copy_file_from_container(self, container_path: str, local_path: str) -> None:
        """Copy a file from the container to the local machine.

        Args:
            container_path: The path to the file in the container.
            local_path: The path to the file on the local machine.
        """
        logger.info(f"{self.name}: Copying file from {container_path} to {local_path}")
        copy_status = subprocess.run(
            [
                "docker",
                "cp",
                f"{self.container_name}:{container_path}",
                local_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        if copy_status.returncode != 0:
            raise RuntimeError(
                f"Failed to copy file from container: {copy_status.stderr}"
            )
