"""Configuration helpers for locating and cloning an Apollo repository."""

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True), override=False)


def get_apollo_root() -> Path:
    """Return the configured local Apollo repository path.

    Returns:
        Absolute path from the `APOLLO_ROOT` environment variable.

    Raises:
        RuntimeError: If `APOLLO_ROOT` is not configured.
    """
    value = os.environ.get("APOLLO_ROOT")
    if not value:
        raise RuntimeError(
            "APOLLO_ROOT is not set. Add it to .env or export it."
        )
    return Path(value).expanduser().resolve()


def get_apollo_git_url() -> str:
    """Return the configured Apollo Git repository URL.

    Returns:
        Repository URL from the `APOLLO_GIT_URL` environment variable.

    Raises:
        RuntimeError: If `APOLLO_GIT_URL` is not configured.
    """
    value = os.environ.get("APOLLO_GIT_URL")
    if not value:
        raise RuntimeError(
            "APOLLO_GIT_URL is not set. Add it to .env or export it."
        )
    return value


def get_apollo_branch() -> str:
    """Return the optional Apollo branch configured by `APOLLO_BRANCH`.

    Returns:
        Branch name, or an empty string when no branch is configured.
    """
    return os.environ.get("APOLLO_BRANCH", "")


def get_apollo_commit_hash() -> str:
    """Return the optional Apollo commit configured by `APOLLO_COMMIT_HASH`.

    Returns:
        Commit hash, or an empty string when no commit is configured.
    """
    return os.environ.get("APOLLO_COMMIT_HASH", "")
