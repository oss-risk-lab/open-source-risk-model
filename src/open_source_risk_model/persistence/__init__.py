"""
Persistence layer for multi-repo graph storage.

This module provides database storage and retrieval for repository graphs,
supporting batch ingestion and cross-repo queries.
"""

from .db import init_database, get_connection
from .errors import DatabaseError, ValidationError, PersistenceError

__all__ = [
    "init_database",
    "get_connection",
    "DatabaseError",
    "ValidationError",
    "PersistenceError",
]
