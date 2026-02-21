"""
Custom exception classes for the persistence layer.

Defines specific exceptions for database operations, validation errors,
and other persistence-related failures.
"""


class PersistenceError(Exception):
    """Base exception for all persistence layer errors."""
    pass


class DatabaseError(PersistenceError):
    """
    Exception raised for database operation failures.
    
    This includes connection failures, query execution errors,
    transaction failures, and other database-level issues.
    """
    pass


class ValidationError(PersistenceError):
    """
    Exception raised for data validation failures.
    
    This includes invalid graph structures, missing required fields,
    invalid references, and other data quality issues that prevent
    storage in the database.
    """
    pass


class JobNotFoundError(PersistenceError):
    """Exception raised when a requested job ID does not exist."""
    pass


class RepositoryNotFoundError(PersistenceError):
    """Exception raised when a requested repository is not in the database."""
    pass
