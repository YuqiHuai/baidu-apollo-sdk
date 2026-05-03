import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True), override=False)


def get_apollo_root() -> Path:
    value = os.environ.get("APOLLO_ROOT")
    if not value:
        raise RuntimeError("APOLLO_ROOT is not set. Add it to .env or export it.")
    return Path(value).expanduser().resolve()


def get_apollo_git_url() -> str:
    value = os.environ.get("APOLLO_GIT_URL")
    if not value:
        raise RuntimeError("APOLLO_GIT_URL is not set. Add it to .env or export it.")
    return value


def get_apollo_branch() -> str:
    return os.environ.get("APOLLO_BRANCH", "")


def get_apollo_commit_hash() -> str:
    return os.environ.get("APOLLO_COMMIT_HASH", "")
