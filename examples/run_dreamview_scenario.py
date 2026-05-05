import time

from baidu_apollo_sdk.apollo_container import ApolloContainer
from baidu_apollo_sdk.apollo_repo import ApolloRepo
from baidu_apollo_sdk.apollo_runtime import ApolloRuntime
from baidu_apollo_sdk.dreamview import Dreamview, DreamviewOperations
from baidu_apollo_sdk.logging import setup_logging

CONTAINER_OWNER = "yuqi"
MAP_NAME = "borregas_ave"
START_POINT = {
    "x": 586971.7121059963,
    "y": 4141267.3710500454,
    "heading": 1.1354430516425942,
}
ROUTE_WAYPOINTS = [
    {
        "x": 586977.4566847438,
        "y": 4141288.868003432,
        "heading": 1.2106031823770664,
    },
    {
        "x": 586981.4482219314,
        "y": 4141302.804574657,
        "heading": 1.1866269624022971,
    },
]


def run_scenario(container: ApolloContainer) -> None:
    runtime = ApolloRuntime(container)
    dreamview = Dreamview(container)
    dreamview.connect()
    dreamview.set_up_for_sim_control()

    runtime.wait_for_node("sim_perfect_control", 0.5)
    dreamview.set_start_point(**START_POINT)

    dreamview.start_module("Planning")
    runtime.wait_for_node("planning", 0.5)

    record_name = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
    runtime.start_recorder(record_name)
    time.sleep(2)

    dreamview.start_routing(ROUTE_WAYPOINTS)
    time.sleep(15)

    runtime.stop_recorder()
    dreamview.stop_module("Planning")
    dreamview.set_operation(DreamviewOperations.RECORD)

    print(f"Dreamview: http://{container.ip_address}:8888")


def main() -> None:
    setup_logging(level="DEBUG", enable_color=True)

    repo = ApolloRepo.from_config()
    container = ApolloContainer(CONTAINER_OWNER, repo.get_path())
    runtime = ApolloRuntime(container)
    runtime.ensure_container(restart=True)
    runtime.set_hd_map(MAP_NAME)
    runtime.bootstrap()

    run_scenario(container)


if __name__ == "__main__":
    main()
