"""Send one routing request to the running Apollo v7 development container."""

from pathlib import Path
from time import sleep

from baidu_apollo_sdk.apollo_container import ApolloContainer
from baidu_apollo_sdk.commands import (
    CommandSender,
    Header,
    LaneFollowCommand,
    Pose,
)
from baidu_apollo_sdk.cyber_rt.bridge import CyberBridge
from baidu_apollo_sdk.cyber_rt.client import CyberClient

APOLLO_V7_PATH = Path("/home/yuqi/ResearchWorkspace/ICSE_2027/apollo-v7.0.1")


def main() -> None:
    """Publish one legacy Apollo v7 routing request through cyber-bridge."""
    container = ApolloContainer("yuqi", APOLLO_V7_PATH, version=7)
    bridge_client = CyberClient(CyberBridge(container))
    sender = CommandSender(bridge_client, version=container.version)

    sender.send_lane_follow(
        LaneFollowCommand(
            start_pose=Pose(x=587178.0, y=4141425.0),
            end_pose=Pose(x=587212.0, y=4141417.0),
            header=Header(
                timestamp_sec=1780296518.136512995,
                module_name="baidu_apollo_sdk_test_send_v7_routing_request",
                sequence_num=5,
            ),
        )
    )
    sleep(1.0)
    print("Sent Apollo v7 routing request to apollo_dev_yuqi")


if __name__ == "__main__":
    main()
