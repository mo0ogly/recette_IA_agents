"""Forensic correlation logging (R6) for the governed-action path.

Every log record emitted on the decision/audit path carries the ``event_id`` and
``agent_id`` of the action it concerns, so an auditor can reconstruct a single
governed action's full flow by filtering the logs on its ``event_id`` (and follow
an approval resolution back via ``correlates_event_id``).

Structured: correlation fields travel through the stdlib ``logging`` ``extra``
mechanism, and an opt-in JSON formatter (``INSPECT_IA_AGENTS_LOG_FORMAT=json``, R5) emits
one JSON object per line for ingestion by any log backend. Adds no source of
non-determinism to the decision path (I4): it only reads fields already present
on the event; it never calls the clock or random.
"""

from __future__ import annotations

import json
import logging
import os

# The correlation keys a forensic query joins on. Only these are promoted onto a
# log record; everything else stays in the human message. event_id is the primary
# join key; correlates_event_id links an approval resolution back to its action.
CORRELATION_FIELDS = (
    "event_id",
    "agent_id",
    "correlates_event_id",
    "kind",
    "verdict",
    "target_system",
    "action_type",
)

ROOT_LOGGER_NAME = "inspect_ia_agents"


class JsonLogFormatter(logging.Formatter):
    """One JSON object per record: level, logger, message + any correlation field."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in CORRELATION_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def log_correlated(
    logger: logging.Logger,
    level: int,
    message: str,
    *,
    event_id: str,
    agent_id: str | None = None,
    **fields: object,
) -> None:
    """Emit a log record carrying event_id/agent_id (+ optional correlation fields).

    Only keys in ``CORRELATION_FIELDS`` are promoted onto the record; unknown or
    None-valued fields are dropped so the structured record stays clean and never
    collides with a reserved ``LogRecord`` attribute."""
    extra: dict[str, object] = {"event_id": event_id}
    if agent_id is not None:
        extra["agent_id"] = agent_id
    for key, value in fields.items():
        if key in CORRELATION_FIELDS and value is not None:
            extra[key] = value
    logger.log(level, message, extra=extra)


def configure_observability_from_env(*, stream: object | None = None) -> logging.Logger:
    """Configure the ``inspect_ia_agents`` logger from the environment (R5).

    ``INSPECT_IA_AGENTS_LOG_FORMAT=json`` -> one JSON line per record (forensic ingestion);
    anything else -> a human text format. ``INSPECT_IA_AGENTS_LOG_LEVEL`` sets the level
    (default INFO). Idempotent: replaces the handler set so repeated calls do not
    stack duplicate handlers. Returns the configured ``inspect_ia_agents`` logger."""
    fmt = os.environ.get("INSPECT_IA_AGENTS_LOG_FORMAT", "text").strip().lower()
    level_name = os.environ.get("INSPECT_IA_AGENTS_LOG_LEVEL", "INFO").strip().upper()
    handler = logging.StreamHandler(stream)  # type: ignore[arg-type]
    if fmt == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    logger.handlers = [handler]
    logger.setLevel(getattr(logging, level_name, logging.INFO))
    logger.propagate = False
    return logger
