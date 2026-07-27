"""Library-safe logging helpers."""

import logging
from collections.abc import Mapping

from mini_infer.engine.request import RequestId

LOGGER_NAME = "mini_infer"


def get_logger(name: str = LOGGER_NAME) -> logging.Logger:
    """Return a library logger without configuring the application's root logger."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    request_id: RequestId,
    fields: Mapping[str, float | int | str] | None = None,
    *,
    exc_info: bool = False,
) -> None:
    """Emit a structured lifecycle event without prompt content."""
    extra: dict[str, float | int | str] = {
        "event": event,
        "request_id": str(request_id),
    }
    if fields is not None:
        extra.update(fields)
    logger.log(level, event, extra=extra, exc_info=exc_info)
