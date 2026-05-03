import time

from baidu_apollo_sdk.apollo_container import ApolloContainer
from baidu_apollo_sdk.apollo_repo import ApolloRepo
from baidu_apollo_sdk.apollo_runtime import ApolloRuntime
from baidu_apollo_sdk.cyber_rt.bridge import CyberBridge
from baidu_apollo_sdk.cyber_rt.client import CyberClient
from baidu_apollo_sdk.cyber_rt.topics import Topics

repo = ApolloRepo.from_config()

repo.clone(True)

ctn = ApolloContainer("yuqi", repo.get_path())
run_time = ApolloRuntime(ctn)
# run_time.ensure_container(False)

cyber_bridge = CyberBridge(ctn.ip_address)

bridge_client = CyberClient(cyber_bridge)


current_time = time.perf_counter()
latest_loc = bridge_client.subscribe_latest(topic=Topics.LocalizationTopic)
bridge_client.start()
print("Subscribed to localization topic, waiting for messages...")
while True:
    if time.perf_counter() - current_time > 5:
        print("Exiting")
        break
    raw = latest_loc.get(block=False)
    if raw is not None:
        loc = Topics.LocalizationTopic.decoder(raw)
        print(
            "Received localization message: "
            f"position=({loc.pose.position.x}, "
            f"{loc.pose.position.y}, "
            f"{loc.pose.position.z}), "
            f"timestamp={loc.header.timestamp_sec}"
        )

bridge_client.stop()
