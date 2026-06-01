"""Send one v11 action request to the HTTP bridge inside Apollo."""

from pathlib import Path

from baidu_apollo_sdk.apollo_container import ApolloContainer
from baidu_apollo_sdk.commands import ActionCommand, CommandSender

APOLLO_V11_PATH = Path("/home/yuqi/ResearchWorkspace/ICSE_2027/apollo-v11.0.0")
ACTION_COMMAND = "PULL_OVER"


def main() -> None:
    """Send one action command through the Apollo v11 HTTP bridge."""
    container = ApolloContainer("yuqi", APOLLO_V11_PATH, version=11)
    sender = CommandSender(
        None,
        version=container.version,
        external_command_service_url=f"http://{container.ip_address}:9091",
    )
    response = sender.send_action(ActionCommand(command=ACTION_COMMAND))
    print(response)
    print(
        "Sent Apollo v11 action request to "
        f"{container.container_name} at {container.ip_address}:9091"
    )


if __name__ == "__main__":
    main()
