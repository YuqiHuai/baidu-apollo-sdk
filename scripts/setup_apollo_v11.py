"""
This script demonstrates ApolloRepo, ApolloContainer, and ApolloRuntime setup.
"""

from baidu_apollo_sdk.apollo_container import ApolloContainer
from baidu_apollo_sdk.apollo_repo import ApolloRepo
from baidu_apollo_sdk.apollo_runtime import ApolloRuntime

repo = ApolloRepo.from_config()

repo.clone(True)

ctn = ApolloContainer("apollo_dev_yuqi", repo.get_path())
run_time = ApolloRuntime(ctn)
run_time.ensure_container()

run_time.build(True)
