"""
Repository snapshot fetcher with adaptive GraphQL batching.

Fetches repository metadata using GitHub GraphQL API v4 with conservative
adaptive batching that adjusts based on query costs and success/failure rates.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from .config import IngestionConfig
from .graphql_client import GraphQLClient
from .models import RepositorySnapshot

logger = logging.getLogger(__name__)


class RepoSnapshotFetcher:
    """Fetches repository snapshots using GraphQL with adaptive batching."""

    def __init__(self, graphql_client: GraphQLClient, config: Optional[IngestionConfig] = None):
        """
        Initialize repository snapshot fetcher.

        Args:
            graphql_client: GraphQL client for API calls
            config: Optional configuration object
        """
        self.client = graphql_client
        self.config = config or IngestionConfig()
        
        # Adaptive batching state
        self.current_batch_size = self.config.get("graphql", "initial_batch_size", default=10)
        self.min_batch_size = self.config.get("graphql", "min_batch_size", default=1)
        self.max_batch_size = self.config.get("graphql", "max_batch_size", default=30)
        self.increase_factor = self.config.get("graphql", "batch_size_increase_factor", default=1.2)
        self.decrease_factor = self.config.get("graphql", "batch_size_decrease_factor", default=0.5)
        
        logger.info(
            f"Initialized RepoSnapshotFetcher with batch size {self.current_batch_size} "
            f"(min: {self.min_batch_size}, max: {self.max_batch_size})"
        )

    def fetch_snapshots(
        self, repo_identifiers: list[str], batch_size: Optional[int] = None
    ) -> list[RepositorySnapshot]:
        """
        Fetch repository snapshots with adaptive batching.

        Args:
            repo_identifiers: List of repository identifiers (owner/repo format)
            batch_size: Optional batch size override (uses adaptive size if None)

        Returns:
            List of RepositorySnapshot objects

        Raises:
            Exception: If fetching fails after retries
        """
        if not repo_identifiers:
            return []
        
        # Use provided batch size or current adaptive size
        effective_batch_size = batch_size if batch_size is not None else self.current_batch_size
        
        logger.info(
            f"Fetching {len(repo_identifiers)} repository snapshots "
            f"with batch size {effective_batch_size}"
        )
        
        all_snapshots = []
        failed_repos = []
        
        # Process repositories in batches
        for i in range(0, len(repo_identifiers), effective_batch_size):
            batch = repo_identifiers[i:i + effective_batch_size]
            
            try:
                # Fetch batch
                batch_snapshots = self._fetch_batch(batch)
                all_snapshots.extend(batch_snapshots)
                
                # On success, cautiously increase batch size (if using adaptive sizing)
                if batch_size is None:
                    self._adjust_batch_size_on_success()
                    
            except Exception as e:
                logger.warning(f"Batch fetch failed for {len(batch)} repos: {e}")
                
                # On failure, reduce batch size and try fallback
                if batch_size is None:
                    self._adjust_batch_size_on_failure()
                
                # Try fetching failed repos individually
                for repo_id in batch:
                    try:
                        snapshot = self.fetch_single(repo_id)
                        all_snapshots.append(snapshot)
                    except Exception as single_error:
                        logger.error(f"Failed to fetch {repo_id}: {single_error}")
                        failed_repos.append(repo_id)
        
        if failed_repos:
            logger.warning(f"Failed to fetch {len(failed_repos)} repositories: {failed_repos}")
        
        logger.info(
            f"Successfully fetched {len(all_snapshots)}/{len(repo_identifiers)} snapshots"
        )
        
        return all_snapshots

    def fetch_single(self, repo_identifier: str) -> RepositorySnapshot:
        """
        Fetch single repository snapshot (fallback for batch failures).

        Args:
            repo_identifier: Repository identifier (owner/repo format)

        Returns:
            RepositorySnapshot object

        Raises:
            Exception: If fetching fails
        """
        logger.debug(f"Fetching single snapshot for {repo_identifier}")
        
        # Parse owner and repo from identifier
        parts = repo_identifier.split("/")
        if len(parts) != 2:
            raise ValueError(f"Invalid repository identifier: {repo_identifier}")
        
        owner, repo = parts
        
        # Build GraphQL query for single repository
        query = """
        query($owner: String!, $repo: String!) {
          repository(owner: $owner, name: $repo) {
            nameWithOwner
            pushedAt
            latestRelease {
              publishedAt
            }
            stargazerCount
            isArchived
            licenseInfo {
              spdxId
            }
            issues(states: OPEN) {
              totalCount
            }
          }
        }
        """
        
        variables = {
            "owner": owner,
            "repo": repo
        }
        
        # Execute query
        response = self.client.execute_query(query, variables)
        
        # Parse response
        # NOTE: an empty "data" can mean a genuine 404 OR an auth/other failure
        # that execute_query did not already raise. Only call it "not found" when
        # the response actually carried a data envelope (i.e. the query executed).
        if "data" not in response:
            raise Exception(
                f"GitHub returned no data envelope for {repo_identifier} "
                "(possible authentication failure — check GITHUB_TOKEN)"
            )
        repo_data = (response.get("data") or {}).get("repository")
        if not repo_data:
            raise Exception(f"Repository not found: {repo_identifier}")
        
        # Convert to RepositorySnapshot
        snapshot = self._parse_repository_data(repo_data, repo_identifier)
        
        return snapshot

    def _fetch_batch(self, repo_identifiers: list[str]) -> list[RepositorySnapshot]:
        """
        Fetch a batch of repository snapshots using GraphQL aliases.

        Args:
            repo_identifiers: List of repository identifiers

        Returns:
            List of RepositorySnapshot objects

        Raises:
            Exception: If batch fetch fails
        """
        if not repo_identifiers:
            return []
        
        # Build batched GraphQL query with aliases
        query_parts = ["query {"]
        
        # Create mapping from index to repo_id for reliable lookup
        index_to_repo = {}
        
        for idx, repo_id in enumerate(repo_identifiers):
            parts = repo_id.split("/")
            if len(parts) != 2:
                logger.warning(f"Skipping invalid repository identifier: {repo_id}")
                continue
            
            owner, repo = parts
            
            # Create alias using just the index (simplest and most reliable)
            alias = f"repo_{idx}"
            index_to_repo[idx] = repo_id
            
            # Add repository query with alias
            query_parts.append(f"""
              {alias}: repository(owner: "{owner}", name: "{repo}") {{
                nameWithOwner
                pushedAt
                latestRelease {{
                  publishedAt
                }}
                stargazerCount
                isArchived
                licenseInfo {{
                  spdxId
                }}
                issues(states: OPEN) {{
                  totalCount
                }}
              }}
            """)
        
        query_parts.append("}")
        query = "\n".join(query_parts)
        
        # Execute batched query
        response = self.client.execute_query(query, variables={})
        
        # Parse response
        data = response.get("data", {})
        snapshots = []
        
        for idx, repo_id in index_to_repo.items():
            alias = f"repo_{idx}"
            
            repo_data = data.get(alias)
            if repo_data:
                try:
                    snapshot = self._parse_repository_data(repo_data, repo_id)
                    snapshots.append(snapshot)
                except Exception as e:
                    logger.warning(f"Failed to parse data for {repo_id}: {e}")
            else:
                logger.warning(f"No data returned for {repo_id}")
        
        return snapshots

    def _parse_repository_data(
        self, repo_data: dict, repo_identifier: str
    ) -> RepositorySnapshot:
        """
        Parse GraphQL repository data into RepositorySnapshot.

        Args:
            repo_data: Repository data from GraphQL response
            repo_identifier: Repository identifier for error messages

        Returns:
            RepositorySnapshot object
        """
        # Extract fields with defaults for missing data
        pushed_at_str = repo_data.get("pushedAt")
        if not pushed_at_str:
            raise ValueError(f"Missing pushedAt for {repo_identifier}")
        
        # Parse timestamps
        pushed_at = datetime.fromisoformat(pushed_at_str.replace("Z", "+00:00"))
        
        latest_release = None
        if repo_data.get("latestRelease"):
            release_str = repo_data["latestRelease"].get("publishedAt")
            if release_str:
                latest_release = datetime.fromisoformat(release_str.replace("Z", "+00:00"))
        
        # Extract other fields
        stargazer_count = repo_data.get("stargazerCount", 0)
        is_archived = repo_data.get("isArchived", False)
        
        license_info = None
        if repo_data.get("licenseInfo"):
            license_info = repo_data["licenseInfo"].get("spdxId")
        
        open_issues_count = 0
        if repo_data.get("issues"):
            open_issues_count = repo_data["issues"].get("totalCount", 0)
        
        # Create RepositorySnapshot
        snapshot = RepositorySnapshot(
            repo_full_name=repo_identifier,
            pushed_at=pushed_at,
            latest_release=latest_release,
            stargazer_count=stargazer_count,
            is_archived=is_archived,
            license_info=license_info,
            open_issues_count=open_issues_count,
            fetched_at=datetime.now(timezone.utc)
        )
        
        return snapshot

    def _adjust_batch_size_on_success(self) -> None:
        """Increase batch size cautiously on successful batch fetch."""
        old_size = self.current_batch_size
        new_size = int(self.current_batch_size * self.increase_factor)
        self.current_batch_size = min(new_size, self.max_batch_size)
        
        if self.current_batch_size != old_size:
            logger.info(
                f"Increased batch size from {old_size} to {self.current_batch_size} "
                f"after successful fetch"
            )

    def _adjust_batch_size_on_failure(self) -> None:
        """Reduce batch size aggressively on batch fetch failure."""
        old_size = self.current_batch_size
        new_size = int(self.current_batch_size * self.decrease_factor)
        self.current_batch_size = max(new_size, self.min_batch_size)
        
        if self.current_batch_size != old_size:
            logger.warning(
                f"Reduced batch size from {old_size} to {self.current_batch_size} "
                f"after failed fetch"
            )
