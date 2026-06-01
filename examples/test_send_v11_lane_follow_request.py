"""Send one v11 lane-follow request to the HTTP bridge inside Apollo."""

from pathlib import Path

from baidu_apollo_sdk.apollo_container import ApolloContainer
from baidu_apollo_sdk.apollo_runtime import ApolloRuntime
from baidu_apollo_sdk.commands import CommandSender, LaneFollowCommand, Pose
from baidu_apollo_sdk.dreamview import Dreamview

APOLLO_V11_PATH = Path("/home/yuqi/ResearchWorkspace/ICSE_2027/apollo-v11.0.0")


def main() -> None:
    """Send one lane-follow command through the Apollo v11 HTTP bridge."""
    container = ApolloContainer("yuqi", APOLLO_V11_PATH, version=11)

    start_pose = Pose(
        x=586182.601515686,
        y=4140316.099658104,
        heading=-1.490966341,
    )
    dreamview = Dreamview(container)
    dreamview.connect()
    dreamview.set_start_point(
        start_pose.x,
        start_pose.y,
        start_pose.heading or 0.0,
    )

    sender = CommandSender(
        None,
        version=container.version,
        lane_follow_service_url=f"http://{container.ip_address}:9091",
    )
    response = sender.send_lane_follow(
        LaneFollowCommand(
            start_pose=start_pose,
            end_pose=Pose(
                x=586181.57591035974,
                y=4140272.142879589,
                heading=-1.6680495250464624,
            ),
            command_id=6,
        )
    )
    print(response)
    print(
        "Sent Apollo v11 lane follow request to "
        f"{container.container_name} at {container.ip_address}:9091"
    )


if __name__ == "__main__":
    main()
