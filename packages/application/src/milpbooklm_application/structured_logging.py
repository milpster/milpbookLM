"""
Structured log output with default redaction (ch18 "Telemetry").

Installs a redacting JSON formatter on the root logger so every record the
installation emits is machine-readable and sensitive:

* the message is scrubbed of obvious credential/token/cookie values
  (:func:`milpbooklm_domain.redaction.scrub_message`);
* any structured ``extra`` fields are recursively redacted by key name
  (:func:`milpbooklm_domain.redaction.redact_structure`);
* the bound correlation/trace identity (ch18 propagation) is attached to every
  record, so logs correlate with requests, jobs and events.

Call :func:`configure_structured_logging` once at each process entry point
(API production app, worker CLI). It is idempotent (replacing only its own
handler) and never touches handlers installed by the host (e.g. uvicorn's).
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from typing import Any

from milpbooklm_domain.redaction import redact_structure, scrub_message
from milpbooklm_domain.telemetry import current_context

HANDLER_MARK = "milpbooklm_redacting_handler"

# stdlib LogRecord attributes that are never user ``extra`` fields.
_RESERVED_ATTRS = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename", "module",
        "exc_info", "exc_text", "stack_info", "lineno", "funcName", "created", "msecs",
        "relativeCreated", "thread", "threadName", "processName", "process", "taskName",
        "message", "asctime",
    }
)


class RedactingJsonFormatter(logging.Formatter):
    """Format one LogRecord as a redacted, single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize the record (message scrubbed, extras redacted, correlation attached)."""
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": scrub_message(record.getMessage()),
        }
        context = current_context()
        if context is not None:
            payload["request_id"] = context.request_id
            if context.trace_id is not None:
                payload["trace_id"] = context.trace_id
                payload["span_id"] = context.span_id
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_ATTRS and not key.startswith("_")
        }
        if extras:
            payload["fields"] = redact_structure(extras)
        if record.exc_info is not None:
            payload["exception"] = "".join(traceback.format_exception(*record.exc_info)).strip()
        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_structured_logging(level: int = logging.INFO, stream: Any = None) -> None:
    """
    Install the redacting JSON handler on the root logger (idempotent).

    Replaces only a handler this function installed previously, so host loggers
    (uvicorn access logs, ...) keep their own handlers; app loggers propagate to
    the root and therefore emit redacted JSON.
    """
    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, HANDLER_MARK, False):
            root.removeHandler(handler)
    if stream is None:
        stream = sys.stderr
    handler = logging.StreamHandler(stream)
    handler.setFormatter(RedactingJsonFormatter())
    setattr(handler, HANDLER_MARK, True)
    root.addHandler(handler)
    root.setLevel(level)
