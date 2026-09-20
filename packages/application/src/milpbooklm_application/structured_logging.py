"""
Structured log output with default redaction (ch18 "Telemetry").

Installs a redacting JSON formatter on every ``milpbooklm_*`` application
namespace so each installation record is machine-readable and sensitive:

* the message is scrubbed of obvious credential/token/cookie values
  (:func:`milpbooklm_domain.redaction.scrub_message`);
* any structured ``extra`` fields are recursively redacted by key name
  (:func:`milpbooklm_domain.redaction.redact_structure`);
* an ``exc_info`` traceback is scrubbed with the same message pass, so secrets
  raised in exception text/frames never leave unredacted;
* the bound correlation/trace identity (ch18 propagation) is attached to every
  record, so logs correlate with requests, jobs and events.

Call :func:`configure_structured_logging` once at each process entry point
(API production app, worker CLI). The handler is installed on every
installation namespace (``milpbooklm_api``, ``milpbooklm_workers``, ...) with
propagation disabled, so an application record is emitted exactly once,
redacted, and can never be duplicated unredacted through a host handler on
the root; host loggers (e.g. uvicorn's) keep their own root paths.
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

# The installation namespaces. Python logger names are dot-hierarchies, so each
# top-level package is its own root-level namespace (NOT a child of "milpbooklm");
# a redacting handler is installed on every one of them, with propagation
# disabled, which is what makes the unredacted-duplicate class of defect
# impossible: app records never reach the root, host loggers never pass here.
APP_LOGGER_NAMES = (
    "milpbooklm_adapters",
    "milpbooklm_api",
    "milpbooklm_application",
    "milpbooklm_contracts",
    "milpbooklm_domain",
    "milpbooklm_workers",
)

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
            # Traceback text (exception message + frames) gets the same scrub as messages:
            # a secret raised in exception text must not escape unredacted.
            payload["exception"] = scrub_message(
                "".join(traceback.format_exception(*record.exc_info))
            ).strip()
        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_structured_logging(level: int = logging.INFO, stream: Any = None) -> None:
    """
    Install the redacting JSON handler on the application loggers (idempotent).

    Every existing handler in an installation namespace is detached first,
    including handlers attached to already-created descendant loggers. Those
    descendants then propagate only to their redacting namespace handler;
    namespace propagation stops there, so host root handlers cannot emit an
    unredacted duplicate. Host logger namespaces remain untouched.
    """
    if stream is None:
        stream = sys.stderr

    app_loggers = tuple(logging.getLogger(name) for name in APP_LOGGER_NAMES)
    managed_loggers = tuple(
        candidate
        for logger_name, candidate in logging.root.manager.loggerDict.items()
        if isinstance(candidate, logging.Logger)
        and any(
            logger_name == namespace or logger_name.startswith(f"{namespace}.")
            for namespace in APP_LOGGER_NAMES
        )
    )
    for managed_logger in managed_loggers:
        for existing_handler in list(managed_logger.handlers):
            managed_logger.removeHandler(existing_handler)
        managed_logger.propagate = True

    for app_logger in app_loggers:
        handler = logging.StreamHandler(stream)
        handler.setFormatter(RedactingJsonFormatter())
        setattr(handler, HANDLER_MARK, True)
        app_logger.addHandler(handler)
        app_logger.setLevel(level)
        app_logger.propagate = False
