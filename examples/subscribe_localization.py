import time

from baidu_apollo_sdk.apollo_container import ApolloContainer
from baidu_apollo_sdk.apollo_repo import ApolloRepo
from baidu_apollo_sdk.cyber_rt.bridge import CyberBridge
from baidu_apollo_sdk.cyber_rt.client import CyberClient
from baidu_apollo_sdk.cyber_rt.topics import Topics


def main() -> None:
    repo = ApolloRepo.from_config()
    repo.clone()

    container = ApolloContainer("yuqi", repo.get_path())
    cyber_bridge = CyberBridge(container)
    bridge_client = CyberClient(cyber_bridge)

    latest_loc = bridge_client.subscribe_latest(topic=Topics.LocalizationTopic)

    current_time = time.perf_counter()
    last_raw: bytes | None = None

    bridge_client.start()
    print("Subscribed to localization topic, waiting for messages...")

    try:
        while time.perf_counter() - current_time <= 5:
            raw = latest_loc.get(block=False)
            if raw is None or raw == last_raw:
                continue

            last_raw = raw
            loc = Topics.LocalizationTopic.decoder(raw)
            position = loc.pose.position
            print(
                "Received localization message: "
                f"position=({position.x}, {position.y}, {position.z}), "
                f"timestamp={loc.header.timestamp_sec}"
            )
    finally:
        bridge_client.stop()

    print("Exiting")


if __name__ == "__main__":
    main()
