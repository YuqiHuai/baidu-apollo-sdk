"""
This script demonstrates ApolloRepo, ApolloContainer, and ApolloRuntime setup.
"""

from baidu_apollo_sdk.apollo_container import ApolloContainer
from baidu_apollo_sdk.apollo_repo import ApolloRepo
from baidu_apollo_sdk.apollo_runtime import ApolloRuntime

repo = ApolloRepo(
    github_url="git@github.com:YuqiHuai/BaiduApollo.git",
    target_dir="/home/yuqi/ResearchWorkspace/ICSE_2027/apollo-v7.0.1",
    branch="r7.0.1",
    commit_hash="919c004d27",
)

repo.clone(True)

ctn = ApolloContainer("yuqi", repo.get_path(), version=7)
run_time = ApolloRuntime(ctn)
run_time.ensure_container(verbose=True)

run_time.build(True)
