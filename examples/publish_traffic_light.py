import time

from baidu_apollo_proto.v11.modules.common_msgs.perception_msgs import (
    traffic_light_detection_pb2,
)

from apollo_instance.apollo_container import ApolloContainer
from apollo_instance.apollo_repo import ApolloRepo
from apollo_instance.cyber_rt.bridge import CyberBridge
from apollo_instance.cyber_rt.client import CyberClient
from apollo_instance.cyber_rt.topics import Topics


def build_traffic_light_detection(sequence_num: int) -> bytes:
    detection = traffic_light_detection_pb2.TrafficLightDetection()
    detection.header.timestamp_sec = time.time()
    detection.header.module_name = "apollo_instance_example"
    detection.header.sequence_num = sequence_num
    detection.contain_lights = True
    detection.camera_id = (
        traffic_light_detection_pb2.TrafficLightDetection.CAMERA_FRONT_LONG
    )
    detection.camera_name = "front_6mm"

    traffic_light = detection.traffic_light.add()
    traffic_light.id = "traffic_light_1"
    traffic_light.color = traffic_light_detection_pb2.TrafficLight.RED
    traffic_light.confidence = 1.0
    traffic_light.tracking_time = 0.0
    traffic_light.blink = False
    traffic_light.remaining_time = 10.0

    return detection.SerializeToString()


def main() -> None:
    repo = ApolloRepo.from_config()
    repo.clone()

    container = ApolloContainer("yuqi", repo.get_path())
    cyber_bridge = CyberBridge(container.ip_address)
    bridge_client = CyberClient(cyber_bridge)

    current_time = time.perf_counter()
    sequence_num = 0

    print("Publishing red traffic light detections...")

    while time.perf_counter() - current_time <= 5:
        raw = build_traffic_light_detection(sequence_num)
        bridge_client.publish(topic=Topics.TrafficLightTopic, msg=raw)
        print(f"Published traffic light detection sequence={sequence_num}")
        sequence_num += 1
        time.sleep(0.5)

    print("Exiting")


if __name__ == "__main__":
    main()
