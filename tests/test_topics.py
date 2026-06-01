"""Tests for version-specific CyberRT topic schemas."""

import subprocess
import sys

import pytest

from baidu_apollo_sdk.cyber_rt.topics import get_topics


def test_default_topics_use_v11_schema() -> None:
    topics = get_topics()

    assert topics.LocalizationTopic.msg_type == (
        "apollo.localization.LocalizationEstimate"
    )
    assert topics.LocalizationTopic.proto_descriptor is not None
    assert (
        topics.LocalizationTopic.proto_descriptor.name
        == "modules/common_msgs/localization_msgs/localization.proto"
    )


def test_v7_topics_use_legacy_schema_in_fresh_process() -> None:
    script = """
from baidu_apollo_sdk.cyber_rt.topics import get_topics
topics = get_topics(7)
print(topics.LocalizationTopic.msg_type)
print(topics.LocalizationTopic.proto_descriptor.name)
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )

    assert result.stdout.splitlines() == [
        "apollo.localization.LocalizationEstimate",
        "modules/localization/proto/localization.proto",
    ]


def test_get_topics_rejects_unsupported_version() -> None:
    with pytest.raises(ValueError, match="Unsupported Apollo version"):
        get_topics(10)


def test_get_topics_rejects_mixed_versions() -> None:
    get_topics(11)

    with pytest.raises(RuntimeError, match="cannot be mixed"):
        get_topics(7)
