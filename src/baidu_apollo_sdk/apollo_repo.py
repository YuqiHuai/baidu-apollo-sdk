"""Utilities for managing the local Apollo source checkout."""

import subprocess
from pathlib import Path

from baidu_apollo_sdk.config import (
    get_apollo_branch,
    get_apollo_commit_hash,
    get_apollo_git_url,
    get_apollo_root,
)


class ApolloRepo:
    """Represents a configured Apollo Git repository checkout.

    Attributes:
        github_url: Git remote URL to clone from.
        target_dir: Local directory where the Apollo repository lives.
        branch: Optional branch to checkout after cloning.
        commit_hash: Optional commit hash to checkout after cloning.
    """

    def __init__(
        self,
        github_url: str,
        target_dir: str | Path,
        branch: str = "",
        commit_hash: str = "",
    ):
        """Initialize repository metadata.

        Args:
            github_url: Git remote URL to clone from.
            target_dir: Local checkout directory.
            branch: Optional branch to checkout.
            commit_hash: Optional commit hash to checkout.
        """
        self.github_url = github_url
        self.target_dir = Path(target_dir)
        self.branch = branch
        self.commit_hash = commit_hash

    @classmethod
    def from_config(cls) -> "ApolloRepo":
        """Create a repository descriptor from environment configuration.

        Returns:
            Repository descriptor populated from `baidu_apollo_sdk.config`.
        """
        return cls(
            get_apollo_git_url(),
            get_apollo_root(),
            branch=get_apollo_branch(),
            commit_hash=get_apollo_commit_hash(),
        )

    def clone(self, stream: bool = False) -> None:
        """Clone the repository if not already cloned.

        Args:
            stream: If True, stream the output of the git command to the console.
                Default is False (capture output).
        """

        if self.is_cloned():
            return

        cmd = [
            "git",
            "clone",
            self.github_url,
            str(self.target_dir),
        ]

        # Only use shallow clone if we don't need a specific commit
        if not self.commit_hash:
            cmd.insert(2, "--depth")
            cmd.insert(3, "1")

        if self.branch:
            cmd.insert(2, "--branch")
            cmd.insert(3, self.branch)

        subprocess.run(cmd, check=True, text=True, capture_output=not stream)

        self.checkout()

    def checkout(self) -> None:
        """Checkout the configured branch or commit.

        Raises:
            RuntimeError: If the repository is not cloned.
            subprocess.CalledProcessError: If the Git checkout command fails.
        """

        if not self.is_cloned():
            raise RuntimeError("Repository not cloned")

        # Decide what to checkout
        ref = None
        if self.commit_hash:
            ref = self.commit_hash
        elif self.branch:
            ref = self.branch

        if not ref:
            return

        subprocess.run(
            ["git", "-C", str(self.target_dir), "checkout", ref],
            check=True,
            text=True,
            capture_output=True,
        )

    def pull(self) -> None:
        """Pull the latest changes into the cloned repository.

        Raises:
            RuntimeError: If the repository is not cloned.
            subprocess.CalledProcessError: If the Git pull command fails.
        """
        if not self.is_cloned():
            raise RuntimeError("Repository not cloned")

        subprocess.run(
            ["git", "-C", str(self.target_dir), "pull"],
            check=True,
            text=True,
            capture_output=True,
        )

    def is_cloned(self) -> bool:
        """Check whether the target directory contains a Git checkout.

        Returns:
            True when the target directory has a `.git` directory.
        """
        return (self.target_dir / ".git").exists()

    def get_path(self) -> Path:
        """Return the local Apollo repository path.

        Returns:
            The configured target directory.
        """
        return self.target_dir
