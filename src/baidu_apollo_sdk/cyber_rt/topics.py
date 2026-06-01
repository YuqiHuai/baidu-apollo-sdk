"""Predefined CyberRT topics for supported Apollo versions."""

# Apollo-style public names such as `LocalizationTopic` are kept for API
# compatibility. Protobuf imports must remain lazy because v7 and v11 generated
# modules contain overlapping descriptors.
# pylint: disable=invalid-name,import-outside-toplevel

from functools import cache
from typing import Any, Protocol, cast

from google.protobuf.message import Message

from baidu_apollo_sdk.version import ApolloVersion, validate_apollo_version

from .channel import Topic
from .decoder import decode_proto

_loaded_version: ApolloVersion | None = None


class TopicNamespace(Protocol):
    """Common topic attributes exposed by each Apollo schema version."""

    ChassisTopic: Topic[Message]
    LocalizationTopic: Topic[Message]
    ObstaclesTopic: Topic[Message]
    TrafficLightTopic: Topic[Message]
    PlanningTopic: Topic[Message]
    RoutingRequestTopic: Topic[Message]


def _topic(
    channel: str, message_type: type[Message], descriptor: Any
) -> Topic[Message]:
    return Topic(
        channel,
        message_type.DESCRIPTOR.full_name,
        decode_proto(message_type),
        descriptor,
    )


def _build_topics_v7() -> type[TopicNamespace]:
    from baidu_apollo_proto.v7.modules.canbus.proto import chassis_pb2
    from baidu_apollo_proto.v7.modules.localization.proto import (
        localization_pb2,
    )
    from baidu_apollo_proto.v7.modules.perception.proto import (
        perception_obstacle_pb2,
        traffic_light_detection_pb2,
    )
    from baidu_apollo_proto.v7.modules.planning.proto import planning_pb2
    from baidu_apollo_proto.v7.modules.routing.proto import routing_pb2

    class TopicsV7:
        """Apollo v7 CyberRT topics."""

        ChassisTopic = _topic(
            "/apollo/canbus/chassis",
            chassis_pb2.Chassis,
            chassis_pb2.DESCRIPTOR,
        )
        LocalizationTopic = _topic(
            "/apollo/localization/pose",
            localization_pb2.LocalizationEstimate,
            localization_pb2.DESCRIPTOR,
        )
        ObstaclesTopic = _topic(
            "/apollo/perception/obstacles",
            perception_obstacle_pb2.PerceptionObstacles,
            perception_obstacle_pb2.DESCRIPTOR,
        )
        TrafficLightTopic = _topic(
            "/apollo/perception/traffic_light",
            traffic_light_detection_pb2.TrafficLightDetection,
            traffic_light_detection_pb2.DESCRIPTOR,
        )
        PlanningTopic = _topic(
            "/apollo/planning",
            planning_pb2.ADCTrajectory,
            planning_pb2.DESCRIPTOR,
        )
        RoutingRequestTopic = _topic(
            "/apollo/routing_request",
            routing_pb2.RoutingRequest,
            routing_pb2.DESCRIPTOR,
        )

    return cast(type[TopicNamespace], TopicsV7)


def _build_topics_v11() -> type[TopicNamespace]:
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

    class TopicsV11:
        """Apollo v11 CyberRT topics."""

        ChassisTopic = _topic(
            "/apollo/canbus/chassis",
            chassis_pb2.Chassis,
            chassis_pb2.DESCRIPTOR,
        )
        LocalizationTopic = _topic(
            "/apollo/localization/pose",
            localization_pb2.LocalizationEstimate,
            localization_pb2.DESCRIPTOR,
        )
        ObstaclesTopic = _topic(
            "/apollo/perception/obstacles",
            perception_obstacle_pb2.PerceptionObstacles,
            perception_obstacle_pb2.DESCRIPTOR,
        )
        TrafficLightTopic = _topic(
            "/apollo/perception/traffic_light",
            traffic_light_detection_pb2.TrafficLightDetection,
            traffic_light_detection_pb2.DESCRIPTOR,
        )
        PlanningTopic = _topic(
            "/apollo/planning",
            planning_pb2.ADCTrajectory,
            planning_pb2.DESCRIPTOR,
        )
        RoutingRequestTopic = _topic(
            "/apollo/routing_request",
            routing_pb2.RoutingRequest,
            routing_pb2.DESCRIPTOR,
        )

    return cast(type[TopicNamespace], TopicsV11)


@cache
def get_topics(version: int = 11) -> type[TopicNamespace]:
    """Return topics backed by protobuf modules for one Apollo version.

    A process should use one Apollo protobuf version. Loading v7 and v11
    generated modules together can conflict in protobuf's global descriptor
    pool.
    """
    global _loaded_version  # pylint: disable=global-statement

    apollo_version: ApolloVersion = validate_apollo_version(version)
    if _loaded_version is not None and _loaded_version != apollo_version:
        raise RuntimeError(
            "Apollo protobuf versions cannot be mixed in one process: "
            f"v{_loaded_version} is already loaded, requested v{apollo_version}"
        )
    _loaded_version = apollo_version
    if apollo_version == 7:
        return _build_topics_v7()
    return _build_topics_v11()


class _DefaultTopics:
    """Lazy backward-compatible alias for Apollo v11 topics."""

    def __getattr__(self, name: str) -> Topic[Message]:
        return cast(Topic[Message], getattr(get_topics(11), name))


Topics = _DefaultTopics()
