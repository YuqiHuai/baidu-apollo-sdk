from apollo_instance.apollo_runtime import ApolloRuntime

from .apollo_repo import ApolloRepo


class ApolloManager:
    def __init__(
        self,
        repo: ApolloRepo,
        runtime: ApolloRuntime,
    ):
        self.repo = repo
        self.runtime = runtime

    def setup(self, restart=False):
        if not self.repo.is_cloned():
            self.repo.clone()

        self.runtime.ensure_container(restart=restart)

    def bootstrap(self):
        self.runtime.bootstrap()
