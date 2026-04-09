"""Repository selection with quota-based ecosystem distribution."""

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from .models import SelectionCriteria, RepositoryCandidate
from .github_client import GitHubClient
from .ecosystem_inference import EcosystemInference
from .priority_scorer import PriorityScorer
from .duplicate_detector import is_duplicate_fork

logger = logging.getLogger(__name__)


class RepositorySelector:
    """Select repositories matching criteria with ecosystem distribution constraints."""
    
    def __init__(self, github_token: str, db_path: str):
        """
        Initialize repository selector.
        
        Args:
            github_token: GitHub personal access token
            db_path: Path to database
        """
        self.github_client = GitHubClient(github_token)
        self.ecosystem_inference = EcosystemInference(self.github_client)
        self.db_path = db_path
    
    def select_repositories(
        self,
        count: int,
        criteria: SelectionCriteria
    ) -> List[RepositoryCandidate]:
        """
        Select repositories matching criteria with two-pass fallback.
        
        Uses quota-based priority selection with explicit quotas for 149 new repos:
        - npm: 38-60 repos (25-40% of 200 total)
        - pypi: 38-60 repos (25-40% of 200 total)
        - go: ≥15 repos (≥10% of 200 total)
        - maven: ≥15 repos (≥10% of 200 total)
        - rubygems: ≥8 repos (≥5% of 200 total)
        
        Two-pass fallback strategy:
        - Pass A: stars >= 1000, recency <= 180 days
        - Pass B (if not enough): stars >= 1000, recency <= 365 days
        - Pass C (if still not enough): stars >= 500, recency <= 365 days
        
        Args:
            count: Number of repositories to select
            criteria: Selection criteria configuration
        
        Returns:
            List of repository candidates with metadata
        """
        logger.info(f"Starting repository selection for {count} repos")
        
        # Phase 1: Query and filter with two-pass fallback
        logger.info("Phase 1: Querying GitHub API")
        all_candidates = self._query_github_repos(criteria.min_stars)
        logger.info(f"Found {len(all_candidates)} candidates from GitHub")
        
        # Two-pass fallback for recency and stars
        candidates = self._apply_two_pass_fallback(all_candidates, count)
        logger.info(f"After two-pass fallback: {len(candidates)} candidates")
        
        if criteria.exclude_forks:
            candidates = [c for c in candidates if not c['fork']]
            logger.info(f"After fork filter: {len(candidates)} candidates")
        
        existing_repos = self._get_existing_repos()
        candidates = [c for c in candidates if c['full_name'] not in existing_repos]
        logger.info(f"After existing repo filter: {len(candidates)} candidates")
        
        # Phase 2: Infer ecosystems
        logger.info("Phase 2: Inferring ecosystems")
        repo_candidates = []
        for i, candidate in enumerate(candidates):
            if i % 10 == 0:
                logger.info(f"Processing candidate {i+1}/{len(candidates)}")
            
            primary_eco, manifests = self.ecosystem_inference.infer_ecosystem(candidate['full_name'])
            
            if primary_eco is None:
                logger.debug(f"Skipping {candidate['full_name']}: no ecosystem detected")
                continue
            
            repo_candidate = RepositoryCandidate(
                full_name=candidate['full_name'],
                stars=candidate['stargazers_count'],
                last_commit_date=datetime.fromisoformat(candidate['pushed_at'].replace('Z', '+00:00')),
                primary_ecosystem=primary_eco,
                manifest_types=manifests,
                has_prod_deps=len(manifests) > 0,  # Simplified: has any manifest
                is_fork=candidate['fork'],
                fork_parent=candidate.get('parent', {}).get('full_name') if candidate.get('parent') else None,
                priority_score=0.0,  # Will be calculated later
                metadata={
                    'description': candidate.get('description', ''),
                    'language': candidate.get('language', ''),
                    'forks_count': candidate.get('forks_count', 0)
                }
            )
            repo_candidates.append(repo_candidate)
        
        logger.info(f"After ecosystem inference: {len(repo_candidates)} candidates")
        
        # Filter by minimum stars
        repo_candidates = [c for c in repo_candidates if c.stars > criteria.min_stars]
        logger.info(f"After star filter: {len(repo_candidates)} candidates")
        
        # Phase 3: Score and deduplicate
        logger.info("Phase 3: Scoring and deduplicating")
        current_distribution = self._get_current_ecosystem_distribution()
        scorer = PriorityScorer(current_distribution, criteria.ecosystem_targets)
        
        for candidate in repo_candidates:
            candidate.priority_score = scorer.calculate_priority_score(candidate)
        
        # Remove duplicates
        repo_candidates = self._remove_duplicates(repo_candidates, existing_repos)
        logger.info(f"After deduplication: {len(repo_candidates)} candidates")
        
        # Phase 4: Quota-based selection
        logger.info("Phase 4: Quota-based selection")
        selected = self._quota_based_selection(repo_candidates, count, criteria)
        logger.info(f"Selected {len(selected)} repositories")
        
        return selected
    
    def _query_github_repos(self, min_stars: int) -> List[Dict]:
        """Query GitHub API for repository candidates."""
        all_repos = []
        
        # Query for different ecosystems to get diverse results
        queries = [
            f"stars:>{min_stars} language:javascript",
            f"stars:>{min_stars} language:typescript",
            f"stars:>{min_stars} language:python",
            f"stars:>{min_stars} language:go",
            f"stars:>{min_stars} language:java",
            f"stars:>{min_stars} language:ruby"
        ]
        
        for query in queries:
            try:
                logger.info(f"Querying GitHub: {query}")
                repos = self.github_client.search_repositories(query, max_results=200)
                logger.info(f"  Found {len(repos)} repos for query: {query}")
                all_repos.extend(repos)
            except Exception as e:
                logger.warning(f"Failed to query '{query}': {e}")
        
        logger.info(f"Total repos from all queries: {len(all_repos)}")
        
        # Deduplicate by full_name
        seen = set()
        unique_repos = []
        for repo in all_repos:
            if repo['full_name'] not in seen:
                seen.add(repo['full_name'])
                unique_repos.append(repo)
        
        logger.info(f"Unique repos after deduplication: {len(unique_repos)}")
        return unique_repos
    
    def _filter_by_recency(self, candidates: List[Dict], max_days_since_commit: int) -> List[Dict]:
        """
        Filter candidates by commit recency.
        
        Keeps repos that were pushed RECENTLY (within last N days).
        Logic: pushed_at >= cutoff_date means "pushed after cutoff" = recent activity.
        """
        cutoff_date = datetime.now() - timedelta(days=max_days_since_commit)
        logger.info(f"Recency filter: keeping repos pushed after {cutoff_date.isoformat()}")
        
        filtered = []
        for i, candidate in enumerate(candidates):
            try:
                pushed_at_str = candidate['pushed_at']
                # Handle timezone-aware datetime
                if pushed_at_str.endswith('Z'):
                    pushed_at = datetime.fromisoformat(pushed_at_str.replace('Z', '+00:00'))
                else:
                    pushed_at = datetime.fromisoformat(pushed_at_str)
                
                # Remove timezone info for comparison (both should be naive)
                pushed_at_naive = pushed_at.replace(tzinfo=None)
                
                # Keep repos pushed AFTER cutoff (recent activity)
                if pushed_at_naive >= cutoff_date:
                    filtered.append(candidate)
                    if i < 3:  # Log first few for debugging
                        logger.debug(f"  KEEP: {candidate['full_name']} pushed {pushed_at_naive.isoformat()}")
                elif i < 3:
                    logger.debug(f"  SKIP: {candidate['full_name']} pushed {pushed_at_naive.isoformat()} (too old)")
            except Exception as e:
                logger.debug(f"Failed to parse date for {candidate.get('full_name', 'unknown')}: {e}")
        
        logger.info(f"Recency filter: kept {len(filtered)}/{len(candidates)} repos")
        return filtered
    
    def _apply_two_pass_fallback(self, all_candidates: List[Dict], target_count: int) -> List[Dict]:
        """
        Apply two-pass fallback strategy to ensure we get enough candidates.
        
        Pass A: stars >= 1000, recency <= 180 days
        Pass B (if not enough): stars >= 1000, recency <= 365 days
        Pass C (if still not enough): stars >= 500, recency <= 365 days
        
        This guarantees progress while preserving quality bar.
        """
        # Pass A: High quality (stars >= 1000, recent within 180 days)
        logger.info("Pass A: Trying stars >= 1000, recency <= 180 days")
        pass_a = self._filter_by_recency(all_candidates, 180)
        pass_a = [c for c in pass_a if c['stargazers_count'] >= 1000]
        logger.info(f"Pass A: {len(pass_a)} candidates")
        
        if len(pass_a) >= target_count * 2:  # Need 2x for ecosystem filtering
            logger.info(f"Pass A succeeded with {len(pass_a)} candidates")
            return pass_a
        
        # Pass B: Relax recency (stars >= 1000, recent within 365 days)
        logger.info("Pass B: Trying stars >= 1000, recency <= 365 days")
        pass_b = self._filter_by_recency(all_candidates, 365)
        pass_b = [c for c in pass_b if c['stargazers_count'] >= 1000]
        logger.info(f"Pass B: {len(pass_b)} candidates")
        
        if len(pass_b) >= target_count * 2:
            logger.info(f"Pass B succeeded with {len(pass_b)} candidates")
            return pass_b
        
        # Pass C: Relax stars (stars >= 500, recent within 365 days)
        logger.info("Pass C: Trying stars >= 500, recency <= 365 days")
        pass_c = self._filter_by_recency(all_candidates, 365)
        pass_c = [c for c in pass_c if c['stargazers_count'] >= 500]
        logger.info(f"Pass C: {len(pass_c)} candidates")
        
        if len(pass_c) >= target_count * 2:
            logger.info(f"Pass C succeeded with {len(pass_c)} candidates")
            return pass_c
        
        # If still not enough, return what we have
        logger.warning(f"All passes completed. Only {len(pass_c)} candidates available (target: {target_count * 2})")
        return pass_c
    
    def _get_existing_repos(self) -> List[str]:
        """Get list of existing repository full names from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT repo_full_name FROM repo_graphs")
        repos = [row[0] for row in cursor.fetchall()]
        conn.close()
        return repos
    
    def _get_current_ecosystem_distribution(self) -> Dict[str, float]:
        """Get current ecosystem distribution from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get total repo count
        cursor.execute("SELECT COUNT(*) FROM repo_graphs")
        total = cursor.fetchone()[0]
        
        if total == 0:
            conn.close()
            return {}
        
        # Get ecosystem counts from dependencies (use registry_type as proxy)
        cursor.execute("""
            SELECT registry_type, COUNT(DISTINCT repo_full_name) as count
            FROM repo_dependencies
            WHERE registry_type IS NOT NULL
            GROUP BY registry_type
        """)
        
        distribution = {}
        for registry_type, count in cursor.fetchall():
            # Map registry to ecosystem
            ecosystem = registry_type.lower() if registry_type else None
            if ecosystem:
                distribution[ecosystem] = count / total
        
        conn.close()
        return distribution
    
    def _language_to_ecosystem(self, language: Optional[str]) -> Optional[str]:
        """Map programming language to package ecosystem."""
        if not language:
            return None
        
        language = language.lower()
        mapping = {
            'javascript': 'npm',
            'typescript': 'npm',
            'python': 'pypi',
            'go': 'go',
            'java': 'maven',
            'ruby': 'rubygems'
        }
        return mapping.get(language)
    
    def _remove_duplicates(
        self,
        candidates: List[RepositoryCandidate],
        existing_repos: List[str]
    ) -> List[RepositoryCandidate]:
        """Remove duplicate candidates."""
        filtered = []
        for candidate in candidates:
            if not is_duplicate_fork(candidate.full_name, candidate.is_fork, existing_repos):
                filtered.append(candidate)
        return filtered
    
    def _quota_based_selection(
        self,
        candidates: List[RepositoryCandidate],
        count: int,
        criteria: SelectionCriteria
    ) -> List[RepositoryCandidate]:
        """
        Select repositories using quota-based priority selection.
        
        Explicit quotas for 149 new repos (to reach 200 total):
        - npm: 38-60 repos (25-40% of 200 total)
        - pypi: 38-60 repos (25-40% of 200 total)
        - go: ≥15 repos (≥10% of 200 total)
        - maven: ≥15 repos (≥10% of 200 total)
        - rubygems: ≥8 repos (≥5% of 200 total)
        """
        # Define ecosystem quotas
        ecosystem_quotas = {
            'npm': {'min': 38, 'max': 60, 'current': 0},
            'pypi': {'min': 38, 'max': 60, 'current': 0},
            'go': {'min': 15, 'max': 200, 'current': 0},
            'maven': {'min': 15, 'max': 200, 'current': 0},
            'rubygems': {'min': 8, 'max': 200, 'current': 0}
        }
        
        selected = []
        
        # Sort by priority (descending)
        candidates.sort(key=lambda r: r.priority_score, reverse=True)
        
        # Phase 4a: Fill minimum quotas first
        for ecosystem in criteria.required_ecosystems:
            ecosystem_candidates = [c for c in candidates if c.primary_ecosystem == ecosystem]
            min_quota = ecosystem_quotas[ecosystem]['min']
            
            for candidate in ecosystem_candidates[:min_quota]:
                if candidate not in selected:
                    selected.append(candidate)
                    ecosystem_quotas[ecosystem]['current'] += 1
        
        # Phase 4b: Fill remaining slots by overall priority respecting max constraints
        for candidate in candidates:
            if len(selected) >= count:
                break
            
            if candidate in selected:
                continue
            
            ecosystem = candidate.primary_ecosystem
            current = ecosystem_quotas.get(ecosystem, {}).get('current', 0)
            max_quota = ecosystem_quotas.get(ecosystem, {}).get('max', count)
            
            if current < max_quota:
                selected.append(candidate)
                ecosystem_quotas[ecosystem]['current'] += 1
        
        return selected
