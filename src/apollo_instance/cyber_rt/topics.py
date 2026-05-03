# topics.py

from typing import cast

from baidu_apollo_proto.v11.modules.common_msgs.chassis_msgs import (
    chassis_pb2,
)
from baidu_apollo_proto.v11.modules.common_msgs.localization_msgs import (
    localization_pb2,
)
from baidu_apollo_proto.v11.modules.common_msgs.perception_msgs import (
    perception_obstacle_pb2,
    traffic_light_detection_pb2,
)
from baidu_apollo_proto.v11.modules.common_msgs.planning_msgs import (
    planning_pb2,
)
from baidu_apollo_proto.v11.modules.common_msgs.routing_msgs import (
    routing_pb2,
)
from google.protobuf.message import Message

from .channel import Topic
from .decoder import decode_proto

Chassis: type[Message] = cast(type[Message], chassis_pb2.Chassis)


LocalizationEstimate: type[Message] = cast(
    type[Message],
    localization_pb2.LocalizationEstimate,
)


PerceptionObstacles: type[Message] = cast(
    type[Message],
    perception_obstacle_pb2.PerceptionObstacles,
)


TrafficLightDetection: type[Message] = cast(
    type[Message],
    traffic_light_detection_pb2.TrafficLightDetection,
)


ADCTrajectory: type[Message] = cast(type[Message], planning_pb2.ADCTrajectory)


RoutingRequest: type[Message] = cast(type[Message], routing_pb2.RoutingRequest)


class Topics:
    ChassisTopic: Topic[Message] = Topic(
        "/apollo/canbus/chassis",
        "apollo.canbus.Chassis",
        decode_proto(Chassis),
    )

    LocalizationTopic: Topic[Message] = Topic(
        "/apollo/localization/pose",
        "apollo.localization.LocalizationEstimate",
        decode_proto(LocalizationEstimate),
    )

    ObstaclesTopic: Topic[Message] = Topic(
        "/apollo/perception/obstacles",
        "apollo.perception.PerceptionObstacles",
        decode_proto(PerceptionObstacles),
    )

    TrafficLightTopic: Topic[Message] = Topic(
        "/apollo/perception/traffic_light",
        "apollo.perception.TrafficLightDetection",
        decode_proto(TrafficLightDetection),
    )

    PlanningTopic: Topic[Message] = Topic(
        "/apollo/planning",
        "apollo.planning.ADCTrajectory",
        decode_proto(ADCTrajectory),
    )

    RoutingRequestTopic: Topic[Message] = Topic(
        "/apollo/routing_request",
        "apollo.routing.RoutingRequest",
        decode_proto(RoutingRequest),
    )
