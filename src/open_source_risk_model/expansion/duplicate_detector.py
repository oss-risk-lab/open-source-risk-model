"""Duplicate repository detection."""

import logging
from typing import List, Set, Dict
import sqlite3

logger = logging.getLogger(__name__)


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    
    if len(s2) == 0:
        return len(s1)
    
    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # Cost of insertions, deletions, or substitutions
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
    
    return previous_row[-1]


def is_similar_name(name1: str, name2: str) -> bool:
    """
    Check if two repository names are similar.
    
    Args:
        name1: First repository full name (owner/repo)
        name2: Second repository full name (owner/repo)
    
    Returns:
        True if names are similar, False otherwise
    """
    owner1, repo1 = name1.split('/')
    owner2, repo2 = name2.split('/')
    
    # Same owner and similar repo name
    if owner1 == owner2 and levenshtein_distance(repo1, repo2) < 3:
        return True
    
    # Exact repo name match (different owners)
    if repo1 == repo2:
        return True
    
    return False


def is_duplicate_fork(candidate_full_name: str, is_fork: bool, existing_repos: List[str]) -> bool:
    """
    Check if candidate is a fork or has similar name to existing repo.
    
    Note: Full dependency graph comparison requires ingestion and is
    deferred to post-ingestion analysis.
    
    Args:
        candidate_full_name: Candidate repository full name
        is_fork: Whether candidate is a fork
        existing_repos: List of existing repository full names
    
    Returns:
        True if duplicate, False otherwise
    """
    # Check if it's a fork
    if is_fork:
        return True
    
    # Check for name similarity with existing repos
    for existing in existing_repos:
        if is_similar_name(candidate_full_name, existing):
            return True
    
    return False


def detect_duplicate_graphs(db_path: str) -> List[List[str]]:
    """
    Detect repositories with identical dependency graphs (post-ingestion).
    
    Computes dependency graph signature (sorted set of direct dependencies)
    for each repository and groups repositories with identical signatures.
    
    Args:
        db_path: Path to database
    
    Returns:
        List of duplicate groups (each group is a list of repo names)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all repositories
    cursor.execute("SELECT repo_full_name FROM repo_graphs")
    repos = [row[0] for row in cursor.fetchall()]
    
    # Compute dependency signature for each repo
    repo_signatures: Dict[str, str] = {}
    
    for repo in repos:
        # Get sorted list of dependencies (package_name + registry_type)
        cursor.execute("""
            SELECT package_name, registry_type
            FROM repo_dependencies
            WHERE repo_full_name = ?
            ORDER BY package_name, registry_type
        """, (repo,))
        
        deps = cursor.fetchall()
        # Create signature as sorted tuple of (package, registry) pairs
        signature = str(sorted(deps))
        repo_signatures[repo] = signature
    
    conn.close()
    
    # Group repositories by signature
    signature_groups: Dict[str, List[str]] = {}
    for repo, signature in repo_signatures.items():
        if signature not in signature_groups:
            signature_groups[signature] = []
        signature_groups[signature].append(repo)
    
    # Return only groups with >1 repository (duplicates)
    duplicate_groups = [
        repos for repos in signature_groups.values()
        if len(repos) > 1
    ]
    
    return duplicate_groups
