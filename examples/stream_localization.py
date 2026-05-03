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

    messages = bridge_client.subscribe(topic=Topics.LocalizationTopic)

    current_time = time.perf_counter()

    bridge_client.start()
    print("Streaming localization messages...")

    try:
        for raw in messages:
            loc = Topics.LocalizationTopic.decoder(raw)
            position = loc.pose.position
            print(
                "Received localization message: "
                f"position=({position.x}, {position.y}, {position.z}), "
                f"timestamp={loc.header.timestamp_sec}"
            )

            if time.perf_counter() - current_time > 5:
                break
    finally:
        bridge_client.stop()

    print("Exiting")


if __name__ == "__main__":
    main()
