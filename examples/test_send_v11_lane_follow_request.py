"""Send one v11 lane-follow request to a running container."""

from pathlib import Path
from time import sleep

from baidu_apollo_sdk.apollo_container import ApolloContainer
from baidu_apollo_sdk.apollo_runtime import ApolloRuntime
from baidu_apollo_sdk.commands import (
    CommandSender,
    Header,
    LaneFollowCommand,
    Pose,
)
from baidu_apollo_sdk.cyber_rt.bridge import CyberBridge
from baidu_apollo_sdk.cyber_rt.client import CyberClient

APOLLO_V11_PATH = Path("/home/yuqi/ResearchWorkspace/ICSE_2027/apollo-v11.0.0")


def main() -> None:
    """Publish one external-command lane-follow request through cyber-bridge."""
    container = ApolloContainer("yuqi", APOLLO_V11_PATH, version=11)
    apollo_runtime = ApolloRuntime(container)
    if "bridge" not in apollo_runtime.list_cyber_nodes():
        apollo_runtime.start_bridge()
        apollo_runtime.wait_for_node("bridge")
    bridge_client = CyberClient(CyberBridge(container))
    sender = CommandSender(bridge_client, version=container.version)

    sender.send_lane_follow(
        LaneFollowCommand(
            start_pose=Pose(x=587178.0, y=4141425.0),
            end_pose=Pose(x=587212.0, y=4141417.0),
            header=Header(
                timestamp_sec=1780296518.136512995,
                module_name="baidu_apollo_sdk_test_send_v11_lane_follow_request",
                sequence_num=5,
            ),
        )
    )
    sleep(1.0)
    print("Sent Apollo v11 lane follow request to apollo_dev_yuqi")


if __name__ == "__main__":
    main()
