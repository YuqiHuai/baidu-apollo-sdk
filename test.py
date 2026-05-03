from apollo_instance.apollo_container import ApolloContainer
from apollo_instance.apollo_repo import ApolloRepo
from apollo_instance.apollo_runtime import ApolloRuntime

repo = ApolloRepo.from_config()

repo.clone(True)

ctn = ApolloContainer("yuqi", repo.get_path())
run_time = ApolloRuntime(ctn)
run_time.ensure_container(False)

run_time.build(True)

# maps = run_time.list_hd_maps()
# print(maps)

# if 'carla_town01' in maps:
#     ctn.remove_directory("/apollo/modules/map/data/carla_town01")
    
# run_time.install_hd_map(
#     "/home/yuqi/ResearchWorkspace/ICSE_2027/apollo-instance/"
#     "data/maps/apollo/carla_town01/base_map.txt",
#     "carla_town01",
# )

# run_time.set_hd_map("carla_town01")