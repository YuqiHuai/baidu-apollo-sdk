"""Logging utilities for the Baidu Apollo SDK."""

import logging
import sys
from typing import Any

from loguru import logger

SDK_NAME = "ApolloSDK"
COMPONENT_NAME = "baidu_apollo_sdk"


def get_logger() -> Any:
    """Return a logger bound with SDK-specific context.

    Usage:
        logger = get_logger()
    """
    return logger.bind(
        component=COMPONENT_NAME,
    )


def _safe_context_value(source: object, attribute: str) -> str:
    try:
        value = getattr(source, attribute)
    except Exception:  # pylint: disable=broad-exception-caught
        return "unknown"
    if value is None:
        return "unknown"
    return str(value)


def container_log_prefix(container: object) -> str:
    """Return a concise container identity for log messages."""
    container_name = _safe_context_value(container, "container_name")
    ip_address = _safe_context_value(container, "ip_address")
    return f"{container_name}@{ip_address}"


def setup_logging(
    level: str = "INFO",
    sink: Any | None = None,
    enable_color: bool = True,
) -> None:
    """Optional helper to configure a default logging format for the SDK.

    This function is opt-in and should be called by the user application,
    not automatically by the SDK.

    Args:
        level: Logging level (e.g. "DEBUG", "INFO")
        sink: Output destination (default: sys.stderr)
        enable_color: Whether to use colored output
    """
    if sink is None:
        sink = sys.stderr

    logger.remove()

    prefix = (
        f"<green>[{SDK_NAME}]</green> " if enable_color else f"[{SDK_NAME}] "
    )

    format_str = (
        prefix
        + "<level><bold>{level.name[0]}</bold></level>"
        + "<cyan>{time:MMDD HH:mm:ss.SSSSSS}</cyan> "
        + "<magenta>{process:5}</magenta> "
        + "<yellow>{file.name}</yellow>:<yellow>{line}</yellow>] "
        + "<level>{message}</level>"
    )

    logger.add(
        sink,
        level=level,
        format=format_str,
        colorize=enable_color,
    )


def enable_std_logging_bridge() -> None:
    """Redirect standard `logging` module logs into Loguru.

    Useful when dependencies (or Apollo-related Python tools) use
    the standard logging library.
    """
    class InterceptHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            level = record.levelname
            logger_opt = logger.opt(
                depth=6,
                exception=record.exc_info,
            )
            logger_opt.log(level, record.getMessage())

    logging.basicConfig(handlers=[InterceptHandler()], level=0)
