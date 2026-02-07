"""Structured logging configuration for the foodplanner application."""

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import datetime
from typing import Any

# Context variables for request/task tracking
request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
task_id_ctx: ContextVar[str | None] = ContextVar("task_id", default=None)
run_id_ctx: ContextVar[int | None] = ContextVar("run_id", default=None)
store_id_ctx: ContextVar[str | None] = ContextVar("store_id", default=None)


class StructuredJsonFormatter(logging.Formatter):
    """JSON formatter for structured logging in production."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add context from context variables
        if request_id := request_id_ctx.get():
            log_data["request_id"] = request_id
        if task_id := task_id_ctx.get():
            log_data["task_id"] = task_id
        if run_id := run_id_ctx.get():
            log_data["run_id"] = run_id
        if store_id := store_id_ctx.get():
            log_data["store_id"] = store_id

        # Add extra fields from the record
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add location info
        log_data["location"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName,
        }

        return json.dumps(log_data)


class ContextualFormatter(logging.Formatter):
    """Human-readable formatter with context for development."""

    def format(self, record: logging.LogRecord) -> str:
        # Build context string
        context_parts = []
        if request_id := request_id_ctx.get():
            context_parts.append(f"req={request_id[:8]}")
        if task_id := task_id_ctx.get():
            context_parts.append(f"task={task_id[:8]}")
        if run_id := run_id_ctx.get():
            context_parts.append(f"run={run_id}")
        if store_id := store_id_ctx.get():
            context_parts.append(f"store={store_id}")

        context_str = f" [{', '.join(context_parts)}]" if context_parts else ""

        # Format the message
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        level = record.levelname.ljust(8)
        message = record.getMessage()

        formatted = f"{timestamp} | {level} | {record.name}{context_str} | {message}"

        # Add exception if present
        if record.exc_info:
            formatted += "\n" + self.formatException(record.exc_info)

        return formatted


class ContextLogger(logging.LoggerAdapter):
    """Logger adapter that automatically includes context variables."""

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        extra = kwargs.get("extra", {})

        # Add context variables to extra
        if request_id := request_id_ctx.get():
            extra["request_id"] = request_id
        if task_id := task_id_ctx.get():
            extra["task_id"] = task_id
        if run_id := run_id_ctx.get():
            extra["run_id"] = run_id
        if store_id := store_id_ctx.get():
            extra["store_id"] = store_id

        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(name: str) -> ContextLogger:
    """Get a context-aware logger for the given module name."""
    logger = logging.getLogger(name)
    return ContextLogger(logger, {})


def configure_logging(
    log_level: str = "INFO",
    json_format: bool | None = None,
    log_file: str | None = None,
) -> None:
    """
    Configure logging for the application.

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON format for logs. If None, auto-detect based on environment.
        log_file: Optional file path to write logs to.
    """
    # Auto-detect JSON format based on environment
    if json_format is None:
        # Use JSON in production (when not running interactively)
        json_format = os.getenv("LOG_FORMAT", "").lower() == "json" or (
            not sys.stdout.isatty() and os.getenv("ENVIRONMENT", "development") == "production"
        )

    # Get log level from environment or parameter
    level_str = os.getenv("LOG_LEVEL", log_level).upper()
    level = getattr(logging, level_str, logging.INFO)

    # Create formatter based on format preference
    if json_format:
        formatter = StructuredJsonFormatter()
    else:
        formatter = ContextualFormatter()

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    root_logger.addHandler(console_handler)

    # Optional file handler
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        root_logger.addHandler(file_handler)

    # Configure log levels for specific modules
    module_levels = {
        "foodplanner": level,
        "foodplanner.ingest": level,
        "foodplanner.tasks": level,
        "celery": logging.WARNING,
        "celery.task": logging.INFO,
        "httpx": logging.WARNING,
        "httpcore": logging.WARNING,
        "sqlalchemy.engine": logging.WARNING,
        "uvicorn": logging.INFO,
        "uvicorn.access": logging.WARNING,
    }

    for module_name, module_level in module_levels.items():
        logging.getLogger(module_name).setLevel(module_level)

    # Log initial configuration
    logger = get_logger(__name__)
    logger.info(
        f"Logging configured: level={level_str}, format={'json' if json_format else 'text'}"
    )


def set_context(
    request_id: str | None = None,
    task_id: str | None = None,
    run_id: int | None = None,
    store_id: str | None = None,
) -> None:
    """Set logging context variables."""
    if request_id is not None:
        request_id_ctx.set(request_id)
    if task_id is not None:
        task_id_ctx.set(task_id)
    if run_id is not None:
        run_id_ctx.set(run_id)
    if store_id is not None:
        store_id_ctx.set(store_id)


def clear_context() -> None:
    """Clear all logging context variables."""
    request_id_ctx.set(None)
    task_id_ctx.set(None)
    run_id_ctx.set(None)
    store_id_ctx.set(None)


class LoggingContext:
    """Context manager for setting logging context."""

    def __init__(
        self,
        request_id: str | None = None,
        task_id: str | None = None,
        run_id: int | None = None,
        store_id: str | None = None,
    ):
        self.request_id = request_id
        self.task_id = task_id
        self.run_id = run_id
        self.store_id = store_id
        self._tokens: dict[str, Any] = {}

    def __enter__(self) -> "LoggingContext":
        if self.request_id is not None:
            self._tokens["request_id"] = request_id_ctx.set(self.request_id)
        if self.task_id is not None:
            self._tokens["task_id"] = task_id_ctx.set(self.task_id)
        if self.run_id is not None:
            self._tokens["run_id"] = run_id_ctx.set(self.run_id)
        if self.store_id is not None:
            self._tokens["store_id"] = store_id_ctx.set(self.store_id)
        return self

    def __exit__(self, *args: Any) -> None:
        for name, token in self._tokens.items():
            ctx_var = {
                "request_id": request_id_ctx,
                "task_id": task_id_ctx,
                "run_id": run_id_ctx,
                "store_id": store_id_ctx,
            }[name]
            ctx_var.reset(token)
