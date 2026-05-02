import sys
import time

from loguru import logger

from apollo_instance.apollo_container import ApolloContainer
from apollo_instance.apollo_repo import ApolloRepo
from apollo_instance.apollo_runtime import ApolloRuntime
from apollo_instance.dreamview import (
    Dreamview,
    DreamviewModes,
    DreamviewOperations,
    DreamviewVehicles,
)

logger.remove()

logger.add(
    sys.stderr,
    format=(
        "<level><bold>{level.name[0]}</bold></level>"  # Severity letter
        "<cyan>{time:MMDD HH:mm:ss.SSSSSS}</cyan> "  # Timestamp
        "<magenta>{process:5}</magenta> "  # PID
        "<yellow>{file.name}</yellow>:<yellow>{line}</yellow>] "  # file:line
        "<level>{message}</level>"  # Message colored by level
    ),
)

repo = ApolloRepo(
    "git@github.com:YuqiHuai/BaiduApollo.git",
    "/home/yuqi/ResearchWorkspace/ICSE_2027/apollo-v11.0.0",
    branch="fix/dreamview_plus_traffic_light",
)

ctn = ApolloContainer("apollo_dev_yuqi", repo.get_path())
run_time = ApolloRuntime(ctn)
run_time.ensure_container(restart=True)
run_time.bootstrap()


def run_scenario(ctn: ApolloContainer):
    dw = Dreamview(ctn)
    dw.connect()
    dw.set_mode(DreamviewModes.PNC)
    dw.set_operation(DreamviewOperations.SIM_CONTROL)
    dw.load_dynamic_models()
    dw.change_dynamic_model()
    _ = dw.set_vehicle(DreamviewVehicles.MKZ_EXAMPLE)

    run_time = ApolloRuntime(ctn)
    run_time.wait_for_node("sim_perfect_control", 0.5)

    dw.set_start_point(586971.7121059963, 4141267.3710500454, 1.1354430516425942)

    dw.start_module("Planning")
    # check for planning node running for 5 seconds
    run_time.wait_for_node("planning", 0.5)

    now = time.time()
    # format time to YYYY-MM-DD_HH-MM-SS
    format_time = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(now))
    run_time.start_recorder(format_time)
    time.sleep(2)

    dw.start_routing(
        [
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
    )
    time.sleep(15)
    run_time.stop_recorder()
    dw.stop_module("Planning")
    dw.set_operation(DreamviewOperations.RECORD)

    print(f"http://{ctn.ip_address}:8888")


run_scenario(ctn)
