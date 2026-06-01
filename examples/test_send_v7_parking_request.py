"""Send one parking request to the running Apollo v7 development container."""

import time
from pathlib import Path
from time import sleep

from baidu_apollo_sdk.apollo_container import ApolloContainer
from baidu_apollo_sdk.apollo_runtime import ApolloRuntime
from baidu_apollo_sdk.commands import (
    CommandSender,
    Header,
    ParkingCommand,
    Pose,
)
from baidu_apollo_sdk.cyber_rt.bridge import CyberBridge
from baidu_apollo_sdk.cyber_rt.client import CyberClient
from baidu_apollo_sdk.map_service import DEFAULT_MAPS_DIR, MapService

APOLLO_V7_PATH = Path("/home/yuqi/ResearchWorkspace/ICSE_2027/apollo-v7.0.1")
SIM_MAP_PATH = (
    DEFAULT_MAPS_DIR / "sunnyvale_with_two_offices" / "sim_map.bin"
)


def main() -> None:
    """Publish one legacy Apollo v7 parking request through cyber-bridge."""
    container = ApolloContainer("yuqi", APOLLO_V7_PATH, version=7)
    apollo_runtime = ApolloRuntime(container)
    if "bridge" not in apollo_runtime.list_cyber_nodes():
        apollo_runtime.start_bridge()
        apollo_runtime.wait_for_node("bridge")
    bridge_client = CyberClient(CyberBridge(container))
    map_service = MapService(version=container.version)
    map_service.load_map_from_file(SIM_MAP_PATH)
    sender = CommandSender(
        bridge_client,
        version=container.version,
        map_service=map_service,
        publication_delay=0.0,
    )

    sender.send_parking(
        ParkingCommand(
            initial_pose=Pose(x=587178.0, y=4141425.0),
            parking_space_id="11545",
            header=Header(
                timestamp_sec=time.time(),
                module_name="baidu_apollo_sdk_test_send_v7_parking_request",
                sequence_num=10,
            ),
            task_header=Header(
                timestamp_sec=time.time(),
                module_name="baidu_apollo_sdk_test_send_v7_parking_request",
                sequence_num=10,
            ),
        )
    )
    sleep(1.0)
    print("Sent Apollo v7 parking request to apollo_dev_yuqi")


if __name__ == "__main__":
    main()
