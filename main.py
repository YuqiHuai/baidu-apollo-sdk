import sys
import time

from loguru import logger

from apollo_instance.container import Container
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

ctn = Container("apollo_dev_yuqi")

ctn.start()

ctn.exec_command("bash apollo.sh build")

ctn.exec_command("bash scripts/bootstrap.sh start_plus")

print("starting dreamview")

dw = Dreamview(ctn)
dw.connect()
dw.set_mode(DreamviewModes.PNC)
dw.set_operation(DreamviewOperations.SIM_CONTROL)
dw.load_dynamic_models()
dw.change_dynamic_model()
vehicle_params = dw.set_vehicle(DreamviewVehicles.MKZ_EXAMPLE)

ctn.wait_for_node("sim_perfect_control")

dw.set_start_point(586971.7121059963, 4141267.3710500454, 1.1354430516425942)

dw.start_module("Planning")
# check for planning node running for 5 seconds
ctn.wait_for_node("planning")

now = time.time()
# format time to YYYY-MM-DD_HH-MM-SS
format_time = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime(now))
ctn.start_recorder(format_time)

dw.start_routing(
    [
        {"x": 586977.4566847438, "y": 4141288.868003432, "heading": 1.2106031823770664},
        {"x": 586981.4482219314, "y": 4141302.804574657, "heading": 1.1866269624022971},
    ]
)
time.sleep(15)
ctn.stop_recorder()
dw.stop_module("Planning")
dw.set_operation(DreamviewOperations.RECORD)
