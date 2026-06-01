"""Coordinate generated Apollo protobuf schema usage within one process."""

from baidu_apollo_sdk.version import ApolloVersion, validate_apollo_version

_loaded_version: ApolloVersion | None = None


def claim_proto_version(version: int) -> ApolloVersion:
    """Claim one Apollo protobuf schema version for the current process."""
    global _loaded_version  # pylint: disable=global-statement

    apollo_version = validate_apollo_version(version)
    if _loaded_version is not None and _loaded_version != apollo_version:
        raise RuntimeError(
            "Apollo protobuf versions cannot be mixed in one process: "
            f"v{_loaded_version} is already loaded, requested v{apollo_version}"
        )
    _loaded_version = apollo_version
    return apollo_version
