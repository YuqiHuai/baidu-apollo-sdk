"""
This script demonstrates ApolloRepo, ApolloContainer, and ApolloRuntime setup.
"""
from apollo_instance.apollo_container import ApolloContainer
from apollo_instance.apollo_repo import ApolloRepo
from apollo_instance.apollo_runtime import ApolloRuntime

repo = ApolloRepo(
    "git@github.com:YuqiHuai/BaiduApollo.git",
    "/home/yuqi/ResearchWorkspace/ICSE_2027/apollo-v11.0.0",
    branch="fix/dreamview_plus_traffic_light",
)

repo.clone(True)

ctn = ApolloContainer("apollo_dev_yuqi", repo.get_path())
run_time = ApolloRuntime(ctn)
run_time.ensure_container()

run_time.build(True)
