"""
Structured logging utilities for graph generation and API requests.

Provides request ID tracking, structured log formatting, and context management.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Dict, Optional

# Context variable to store request ID across async boundaries
request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


class StructuredLogger:
    """
    Structured logger that adds request ID and context to all log entries.
    
    Usage:
        logger = StructuredLogger(__name__)
        logger.info("Graph generation started", repo="owner/repo", config=config)
    """
    
    def __init__(self, name: str):
        """
        Initialize structured logger.
        
        Args:
            name: Logger name (typically __name__)
        """
        self.logger = logging.getLogger(name)
    
    def _format_message(self, message: str, **context) -> str:
        """
        Format log message with request ID and context.
        
        Args:
            message: Base log message
            **context: Additional context key-value pairs
        
        Returns:
            Formatted message string
        """
        request_id = request_id_var.get()
        
        # Build context string
        parts = []
        if request_id:
            parts.append(f"request_id={request_id}")
        
        for key, value in context.items():
            # Handle special types
            if isinstance(value, dict):
                # Flatten dict for readability
                value_str = ", ".join(f"{k}={v}" for k, v in value.items())
                parts.append(f"{key}=({value_str})")
            else:
                parts.append(f"{key}={value}")
        
        if parts:
            context_str = " | " + " | ".join(parts)
        else:
            context_str = ""
        
        return f"{message}{context_str}"
    
    def debug(self, message: str, **context):
        """Log debug message with context."""
        self.logger.debug(self._format_message(message, **context))
    
    def info(self, message: str, **context):
        """Log info message with context."""
        self.logger.info(self._format_message(message, **context))
    
    def warning(self, message: str, **context):
        """Log warning message with context."""
        self.logger.warning(self._format_message(message, **context))
    
    def error(self, message: str, exc_info: bool = False, **context):
        """Log error message with context."""
        self.logger.error(self._format_message(message, **context), exc_info=exc_info)


def generate_request_id() -> str:
    """
    Generate a unique request ID.
    
    Returns:
        UUID-based request ID
    """
    return str(uuid.uuid4())


def set_request_id(request_id: str) -> None:
    """
    Set request ID in context.
    
    Args:
        request_id: Request ID to set
    """
    request_id_var.set(request_id)


def get_request_id() -> Optional[str]:
    """
    Get current request ID from context.
    
    Returns:
        Current request ID or None
    """
    return request_id_var.get()


def clear_request_id() -> None:
    """Clear request ID from context."""
    request_id_var.set(None)


# Event types for structured logging
class LogEvent:
    """Log event types for graph generation."""
    
    # Graph generation events
    GRAPH_GENERATION_STARTED = "graph_generation_started"
    GRAPH_GENERATION_COMPLETED = "graph_generation_completed"
    GRAPH_GENERATION_FAILED = "graph_generation_failed"
    
    # External API call events
    EXTERNAL_API_CALL_STARTED = "external_api_call_started"
    EXTERNAL_API_CALL_COMPLETED = "external_api_call_completed"
    EXTERNAL_API_CALL_FAILED = "external_api_call_failed"
    
    # Cache events
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    CACHE_WRITE = "cache_write"
    CACHE_WRITE_FAILED = "cache_write_failed"
    
    # Validation events
    VALIDATION_FAILED = "validation_failed"
    VALIDATION_PASSED = "validation_passed"


def log_event(
    logger: StructuredLogger,
    event_type: str,
    level: str = "info",
    **context
) -> None:
    """
    Log a structured event.
    
    Args:
        logger: Structured logger instance
        event_type: Event type (use LogEvent constants)
        level: Log level (debug, info, warning, error)
        **context: Additional context for the event
    """
    # Add timestamp and event type to context
    context["event"] = event_type
    context["timestamp"] = datetime.now(timezone.utc).isoformat()
    
    # Log at appropriate level
    if level == "debug":
        logger.debug(f"Event: {event_type}", **context)
    elif level == "info":
        logger.info(f"Event: {event_type}", **context)
    elif level == "warning":
        logger.warning(f"Event: {event_type}", **context)
    elif level == "error":
        logger.error(f"Event: {event_type}", **context)
