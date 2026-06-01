"""Apollo version helpers shared by SDK components."""

from typing import Literal, cast

ApolloVersion = Literal[7, 11]
SUPPORTED_APOLLO_VERSIONS = (7, 11)


def validate_apollo_version(version: int) -> ApolloVersion:
    """Validate and narrow an Apollo major version."""
    if version not in SUPPORTED_APOLLO_VERSIONS:
        raise ValueError(f"Unsupported Apollo version: {version}")
    return cast(ApolloVersion, version)
