class ApolloRepo:
    APOLLO_GITHUB_URL = "https://github.com/ApolloAuto/apollo.git"

    def __init__(self, commit_hash: str = ""):
        self.commit_hash = commit_hash

    def clone(self, target_dir: str):
        pass

    def checkout(self):
        pass

    def is_cloned(self, target_dir: str) -> bool:
        pass

    def get_path(self):
        pass
