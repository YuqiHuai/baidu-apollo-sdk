import time

from apollo_instance.apollo_container import ApolloContainer
from apollo_instance.apollo_repo import ApolloRepo
from apollo_instance.cyber_rt.bridge import CyberBridge
from apollo_instance.cyber_rt.client import CyberClient
from apollo_instance.cyber_rt.topics import Topics


def main() -> None:
    repo = ApolloRepo.from_config()
    repo.clone()

    container = ApolloContainer("yuqi", repo.get_path())
    cyber_bridge = CyberBridge(container.ip_address)
    bridge_client = CyberClient(cyber_bridge)

    latest_loc = bridge_client.subscribe_latest(channel=Topics.LocalizationTopic)
    latest_chassis = bridge_client.subscribe_latest(channel=Topics.ChassisTopic)

    current_time = time.perf_counter()
    last_loc_raw: bytes | None = None
    last_chassis_raw: bytes | None = None

    bridge_client.start()
    print("Subscribed to localization and chassis topics, waiting for messages...")

    try:
        while time.perf_counter() - current_time <= 5:
            loc_raw = latest_loc.get(block=False)
            if loc_raw is not None and loc_raw != last_loc_raw:
                last_loc_raw = loc_raw
                loc = Topics.LocalizationTopic.decoder(loc_raw)
                position = loc.pose.position
                print(
                    "Localization: "
                    f"position=({position.x}, {position.y}, {position.z}), "
                    f"timestamp={loc.header.timestamp_sec}"
                )

            chassis_raw = latest_chassis.get(block=False)
            if chassis_raw is not None and chassis_raw != last_chassis_raw:
                last_chassis_raw = chassis_raw
                chassis = Topics.ChassisTopic.decoder(chassis_raw)
                print(
                    "Chassis: "
                    f"speed_mps={chassis.speed_mps}, "
                    f"driving_mode={chassis.driving_mode}, "
                    f"timestamp={chassis.header.timestamp_sec}"
                )
    finally:
        bridge_client.stop()

    print("Exiting")


if __name__ == "__main__":
    main()
