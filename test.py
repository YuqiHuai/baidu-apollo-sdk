from baidu_apollo_proto.v7.modules.map.proto.map_pb2 import Map
from pathlib import Path

map_root = Path("/home/yuqi/ResearchWorkspace/CADRI/approaches/DoppelTest/data/maps")
map = Map()

for map_name in map_root.iterdir():
    if map_name.is_file():
        continue
    if map_name.name != 'sunnyvale_with_two_offices':
        continue
    map_bin = map_name / "base_map.bin"
    assert map_bin.exists(), f"{map_bin} does not exist"

    print(f"Parsing map from {map_bin}")

    with open(map_bin, 'rb') as f:
        map.ParseFromString(f.read())

        parking_spaces = map.parking_space
        print(f"Number of parking spaces: {len(parking_spaces)}")

        for parking_space in parking_spaces:
            print('=' * 20)
            print(parking_space)

        for lane in map.lane:
            if lane.id.id == "11565dup1_1_-1":
                print('=' * 20)
                print(lane)

# with open('map.bin', 'rb') as f:
    # map.ParseFromString(f.read())
