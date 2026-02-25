"""
Query module for intent-based dependency graph queries.

This module provides a safe query interface that:
1. Never generates SQL from LLM output
2. Uses strict intent allowlist
3. Computes results on-the-fly from database
"""
