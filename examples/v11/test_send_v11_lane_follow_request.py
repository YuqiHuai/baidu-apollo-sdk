"""Send one v11 lane-follow request to the HTTP bridge inside Apollo."""

from pathlib import Path
from time import sleep

from baidu_apollo_sdk.apollo_container import ApolloContainer
from baidu_apollo_sdk.commands import CommandSender, LaneFollowCommand, Pose
from baidu_apollo_sdk.dreamview import Dreamview

APOLLO_V11_PATH = Path("/home/yuqi/ResearchWorkspace/ICSE_2027/apollo-v11.0.0")


def main() -> None:
    """Send one lane-follow command through the Apollo v11 HTTP bridge."""
    container = ApolloContainer("yuqi", APOLLO_V11_PATH, version=11)

    start_pose = Pose(
        x=587169.516887442,
        y=4141458.210908933,
        heading=-1.829251263,
    )
    dreamview = Dreamview(container)
    dreamview.connect()
    dreamview.set_start_point(
        start_pose.x,
        start_pose.y,
        start_pose.heading or 0.0,
    )
    

    sleep(1.0)

    sender = CommandSender(
        None,
        version=container.version,
        lane_follow_service_url=f"http://{container.ip_address}:9091",
    )
    response = sender.send_lane_follow(
        LaneFollowCommand(
            start_pose=start_pose,
            end_pose=Pose(
                x=587198.628772753,
                y=4141421.025978817,
                heading=-0.368695903,
            ),
            command_id=20,
        )
    )
    print(response)
    print(
        "Sent Apollo v11 lane follow request to "
        f"{container.container_name} at {container.ip_address}:9091"
    )


if __name__ == "__main__":
    main()
