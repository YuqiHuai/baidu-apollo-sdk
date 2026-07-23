"""Tests for version-aware semantic Apollo commands."""

import io
import json
import subprocess
import sys
from email.message import Message
from types import SimpleNamespace
from typing import Any
from urllib.error import HTTPError

import pytest
from baidu_apollo_proto.v11.modules.common_msgs.routing_msgs import routing_pb2
from shapely.geometry import Point

from baidu_apollo_sdk.commands import (
    ActionCommand,
    CommandSender,
    Header,
    LaneFollowCommand,
    ParkingCommand,
    Pose,
    Publication,
)
from baidu_apollo_sdk.cyber_rt.channel import Topic
from baidu_apollo_sdk.map_service import ParkingSpaceExtraInfo


class FakeHttpResponse:
    """Return a fixed body from a mocked HTTP request."""

    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        return None

    def read(self) -> bytes:
        return self.body


class FakeCyberClient:
    """Record published messages without opening a bridge socket."""

    def __init__(self) -> None:
        self.publications: list[tuple[Topic[Any], bytes]] = []

    def publish(self, topic: Topic[Any], msg: bytes) -> None:
        """Record one publication."""
        self.publications.append((topic, msg))


class FakeMapService:
    """Provide deterministic parking metadata without loading HD-map assets."""

    def __init__(self) -> None:
        self.parking_space = SimpleNamespace(
            polygon=SimpleNamespace(
                point=[
                    SimpleNamespace(x=0.0, y=0.0, z=0.0),
                    SimpleNamespace(x=4.0, y=0.0, z=0.0),
                    SimpleNamespace(x=4.0, y=2.0, z=0.4),
                    SimpleNamespace(x=0.0, y=2.0, z=0.4),
                ]
            )
        )

    def get_parking_space_by_id(self, parking_space_id: str) -> Any:
        """Return one known parking-space polygon."""
        assert parking_space_id == "parking-1"
        return self.parking_space

    def calc_parking_space_extra_info(
        self, parking_space: Any
    ) -> ParkingSpaceExtraInfo:
        """Return deterministic routing metadata for the known polygon."""
        assert parking_space is self.parking_space
        return ParkingSpaceExtraInfo(
            order=(0, 1, 2, 3),
            parking_type=0,
            lane_width=8.0,
            routing_end_point=Point(10.0, 11.0),
            lane_id="lane-1",
        )


def test_v11_lane_follow_uses_external_command_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[Any] = []

    def fake_urlopen(request: Any) -> FakeHttpResponse:
        requests.append(request)
        return FakeHttpResponse(b'{"accepted": true, "request_id": "abc-123"}')

    monkeypatch.setattr(
        "baidu_apollo_sdk.commands.sender.urlopen",
        fake_urlopen,
    )
    sender = CommandSender(
        None,
        version=11,
        external_command_service_url="http://10.0.0.9:9091",
    )
    response = sender.send_lane_follow(
        LaneFollowCommand(
            start_pose=Pose(1.0, 2.0, 0.1),
            waypoints=(Pose(3.0, 4.0),),
            end_pose=Pose(5.0, 6.0, 0.2),
            header=Header(123.5, "test", 7),
            command_id=5,
            target_speed=2.0,
        )
    )

    assert len(requests) == 1
    request = requests[0]
    assert request.full_url == "http://10.0.0.9:9091/lane_follow"
    assert request.get_method() == "POST"
    assert request.headers["Content-type"] == "application/json"
    assert json.loads(request.data.decode("utf-8")) == {
        "command_id": 5,
        "endPose": {"x": 5.0, "y": 6.0, "heading": 0.2},
        "isStartPoseSet": True,
        "target_speed": 2.0,
        "wayPoint": [
            {"x": 1.0, "y": 2.0, "heading": 0.1},
            {"x": 3.0, "y": 4.0},
        ],
    }
    assert response == {"accepted": True, "request_id": "abc-123"}


def test_v11_lane_follow_returns_http_error_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(request: Any) -> None:
        raise HTTPError(
            request.full_url,
            503,
            "Service Unavailable",
            hdrs=Message(),
            fp=io.BytesIO(b'{"ok": false, "error": "no response"}'),
        )

    monkeypatch.setattr(
        "baidu_apollo_sdk.commands.sender.urlopen",
        fake_urlopen,
    )
    sender = CommandSender(
        None,
        version=11,
        external_command_service_url="http://10.0.0.9:9091",
    )
    response = sender.send_lane_follow(
        LaneFollowCommand(
            start_pose=Pose(1.0, 2.0, 0.1),
            end_pose=Pose(5.0, 6.0, 0.2),
            target_speed=2.0,
        )
    )

    assert response == {"ok": False, "error": "no response"}


def test_v11_parking_command_uses_valet_parking_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[Any] = []

    def fake_urlopen(request: Any) -> FakeHttpResponse:
        requests.append(request)
        return FakeHttpResponse(b'{"ok": true}')

    monkeypatch.setattr(
        "baidu_apollo_sdk.commands.sender.urlopen",
        fake_urlopen,
    )
    sender = CommandSender(
        None,
        version=11,
        external_command_service_url="http://10.0.0.9:9091",
    )

    response = sender.send_parking(
        ParkingCommand(
            initial_pose=Pose(1.0, 2.0, 0.1),
            parking_space_id="parking-1",
        )
    )

    assert len(requests) == 1
    request = requests[0]
    assert request.full_url == "http://10.0.0.9:9091/valet_parking"
    assert json.loads(request.data.decode("utf-8")) == {
        "parking_spot_id": "parking-1"
    }
    assert response == {"ok": True}


@pytest.mark.parametrize("action", ("PULL_OVER", "STOP", "START"))
def test_v11_action_command_uses_action_service(
    action: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[Any] = []

    def fake_urlopen(request: Any) -> FakeHttpResponse:
        requests.append(request)
        return FakeHttpResponse(b'{"ok": true}')

    monkeypatch.setattr(
        "baidu_apollo_sdk.commands.sender.urlopen",
        fake_urlopen,
    )
    sender = CommandSender(
        None,
        version=11,
        external_command_service_url="http://10.0.0.9:9091",
    )

    response = sender.send_action(ActionCommand(command=action))

    assert len(requests) == 1
    request = requests[0]
    assert request.full_url == "http://10.0.0.9:9091/action"
    assert json.loads(request.data.decode("utf-8")) == {
        "command": action
    }
    assert response == {"ok": True}


def test_v11_action_command_rejects_v7_only_command() -> None:
    sender = CommandSender(
        None,
        version=11,
        external_command_service_url="http://10.0.0.9:9091",
    )

    with pytest.raises(
        ValueError,
        match=(
            "Apollo v11 action command 'RESUME_CRUISE' is not supported"
        ),
    ):
        sender.send_action(ActionCommand(command="RESUME_CRUISE"))


def test_v11_commands_require_service_url() -> None:
    sender = CommandSender(None, version=11)

    with pytest.raises(RuntimeError, match="external_command_service_url"):
        sender.send_lane_follow(
            LaneFollowCommand(
                start_pose=Pose(1.0, 2.0, 0.1),
                end_pose=Pose(5.0, 6.0, 0.2),
            )
        )


def test_v7_parking_command_requires_map_service_in_fresh_process() -> None:
    script = """
from baidu_apollo_sdk.commands import CommandSender, ParkingCommand, Pose

class FakeClient:
    def publish(self, topic, message):
        pass

try:
    CommandSender(FakeClient(), version=7).send_parking(
        ParkingCommand(Pose(1.0, 2.0), "parking-1")
    )
except RuntimeError as exc:
    print(exc)
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "Parking commands require a map service"


def test_v7_action_command_uses_planning_pad_in_fresh_process() -> None:
    script = """
import json
from baidu_apollo_sdk.commands import ActionCommand, CommandSender
from baidu_apollo_proto.v7.modules.planning.proto.pad_msg_pb2 import PadMessage

class FakeClient:
    def __init__(self):
        self.publications = []

    def publish(self, topic, message):
        self.publications.append((topic, message))

results = {}
for action in ("PULL_OVER", "STOP", "RESUME_CRUISE"):
    client = FakeClient()
    CommandSender(client, version=7).send_action(
        ActionCommand(command=action)
    )
    message = PadMessage()
    message.ParseFromString(client.publications[0][1])
    results[action] = {
        "channel": client.publications[0][0].channel,
        "action": message.action,
    }

try:
    CommandSender(FakeClient(), version=7).send_action(
        ActionCommand(command="START")
    )
except ValueError as exc:
    results["START_ERROR"] = str(exc)

print(json.dumps(results))
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == {
        "PULL_OVER": {"channel": "/apollo/planning/pad", "action": 3},
        "STOP": {"channel": "/apollo/planning/pad", "action": 4},
        "RESUME_CRUISE": {
            "channel": "/apollo/planning/pad",
            "action": 5,
        },
        "START_ERROR": (
            "Apollo v7 action command 'START' is not supported; "
            "supported commands: CHANGE_LEFT, CHANGE_RIGHT, FOLLOW, "
            "PULL_OVER, RESUME_CRUISE, STOP"
        ),
    }



def test_sender_waits_between_multi_message_publications(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeCyberClient()
    sleeps: list[float] = []
    monkeypatch.setattr(
        "baidu_apollo_sdk.commands.sender.time.sleep",
        sleeps.append,
    )
    sender = CommandSender(client, publication_delay=0.25)
    first = Publication(
        Topic("/a", "apollo.A", bytes),
        routing_pb2.RoutingRequest(),
    )
    second = Publication(
        Topic("/b", "apollo.B", bytes),
        routing_pb2.RoutingRequest(),
    )

    sender._publish_all((first, second))

    assert [topic.channel for topic, _ in client.publications] == ["/a", "/b"]
    assert sleeps == [0.25]


def test_v7_lane_follow_uses_legacy_routing_request_in_fresh_process() -> None:
    script = """
import json
from baidu_apollo_sdk.commands import Header, LaneFollowCommand, Pose
from baidu_apollo_sdk.commands.sender import create_command_encoder

publication = create_command_encoder(7).encode_lane_follow(
    LaneFollowCommand(
        start_pose=Pose(1.0, 2.0, 0.1),
        waypoints=(Pose(3.0, 4.0),),
        end_pose=Pose(5.0, 6.0, 0.2),
        header=Header(123.5, "test", 7),
    )
)[0]
request = publication.message
print(json.dumps({
    "channel": publication.topic.channel,
    "descriptor": publication.topic.proto_descriptor.name,
    "header": {
        "timestamp_sec": request.header.timestamp_sec,
        "module_name": request.header.module_name,
        "sequence_num": request.header.sequence_num,
    },
    "poses": [[point.pose.x, point.pose.y] for point in request.waypoint],
}))
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == {
        "channel": "/apollo/routing_request",
        "descriptor": "modules/routing/proto/routing.proto",
        "header": {
            "timestamp_sec": 123.5,
            "module_name": "test",
            "sequence_num": 7,
        },
        "poses": [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]],
    }


def test_v7_parking_command_encodes_derived_metadata_in_fresh_process() -> None:
    script = """
import json
from types import SimpleNamespace
from shapely.geometry import Point
from baidu_apollo_proto.v7.modules.routing.proto.routing_pb2 import (
    RoutingRequest,
)
from baidu_apollo_proto.v7.modules.task_manager.proto.task_manager_pb2 import (
    Task,
)
from baidu_apollo_sdk.commands import (
    CommandSender,
    Header,
    ParkingCommand,
    Pose,
)
from baidu_apollo_sdk.map_service import ParkingSpaceExtraInfo

class FakeClient:
    def __init__(self):
        self.publications = []

    def publish(self, topic, message):
        self.publications.append((topic, message))

parking_space = SimpleNamespace(
    polygon=SimpleNamespace(
        point=[
            SimpleNamespace(x=0.0, y=0.0, z=0.0),
            SimpleNamespace(x=4.0, y=0.0, z=0.0),
            SimpleNamespace(x=4.0, y=2.0, z=0.4),
            SimpleNamespace(x=0.0, y=2.0, z=0.4),
        ]
    )
)
map_service = SimpleNamespace(
    get_parking_space_by_id=lambda parking_space_id: parking_space,
    calc_parking_space_extra_info=lambda value: ParkingSpaceExtraInfo(
        order=(0, 1, 2, 3),
        parking_type=0,
        lane_width=8.0,
        routing_end_point=Point(10.0, 11.0),
        lane_id="lane-1",
    ),
)
client = FakeClient()
CommandSender(
    client,
    version=7,
    map_service=map_service,
    publication_delay=0.0,
).send_parking(
    ParkingCommand(
        Pose(1.0, 2.0),
        "parking-1",
        header=Header(123.5, "dreamview", 8),
        task_header=Header(124.5, "dreamview", 3),
    )
)
request = RoutingRequest()
request.ParseFromString(client.publications[0][1])
task = Task()
task.ParseFromString(client.publications[1][1])
print(json.dumps({
    "channels": [topic.channel for topic, _ in client.publications],
    "poses": [[point.pose.x, point.pose.y] for point in request.waypoint],
    "has_lane_id": request.waypoint[1].HasField("id"),
    "parking_space_id": request.parking_info.parking_space_id,
    "parking_point": [
        request.parking_info.parking_point.x,
        request.parking_info.parking_point.y,
        request.parking_info.parking_point.z,
    ],
    "task_header": {
        "timestamp_sec": task.header.timestamp_sec,
        "module_name": task.header.module_name,
        "sequence_num": task.header.sequence_num,
    },
    "task_name": task.task_name,
    "task_type": task.task_type,
    "lane_width": task.parking_routing_task.lane_width,
    "task_has_routing_header": (
        task.parking_routing_task.routing_request.HasField("header")
    ),
    "task_parking_space_id": (
        task.parking_routing_task.routing_request
        .parking_info.parking_space_id
    ),
}))
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert json.loads(result.stdout) == {
        "channels": ["/apollo/routing_request", "/apollo/task_manager"],
        "poses": [[1.0, 2.0], [10.0, 11.0]],
        "has_lane_id": False,
        "parking_space_id": "parking-1",
        "parking_point": [2.0, 1.0, 0.2],
        "task_header": {
            "timestamp_sec": 124.5,
            "module_name": "dreamview",
            "sequence_num": 3,
        },
        "task_name": "parking_routing_task",
        "task_type": 1,
        "lane_width": 8.0,
        "task_has_routing_header": False,
        "task_parking_space_id": "parking-1",
    }
