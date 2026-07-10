"""
Contributors fetcher for GitHub API.

Fetches contributor data using REST API endpoints.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from .models import ContributorRecord, WeeklyActivity
from .rest_client import RESTClient

logger = logging.getLogger(__name__)


class ContributorsFetcher:
    """Fetches contributor data from GitHub REST API."""

    def __init__(self, rest_client: RESTClient, config: Optional[dict] = None):
        """
        Initialize contributors fetcher.

        Args:
            rest_client: REST client for API calls
            config: Optional configuration dict
        """
        self.rest_client = rest_client
        self.config = config or {}

    def fetch_contributors(self, repo_identifier: str) -> list[ContributorRecord]:
        """
        Fetch contributor data with pagination.

        Args:
            repo_identifier: Repository in owner/repo format

        Returns:
            List of ContributorRecord objects

        Raises:
            Exception: If fetching fails
        """
        logger.info(f"Fetching contributors for {repo_identifier}")

        # Parse repo identifier
        if "/" not in repo_identifier:
            raise ValueError(
                f"Invalid repository identifier: {repo_identifier}. "
                "Expected format: owner/repo"
            )

        owner, repo = repo_identifier.split("/", 1)

        # Fetch basic contributor list
        endpoint = f"/repos/{owner}/{repo}/contributors"
        contributors_data = []

        try:
            # Use pagination to get all contributors
            max_pages = self.config.get("max_pages_per_request", 10)
            for page_data in self.rest_client.paginate(endpoint, max_pages=max_pages):
                if isinstance(page_data, list):
                    contributors_data.extend(page_data)
                else:
                    logger.warning(
                        f"Unexpected response format for {endpoint}: {type(page_data)}"
                    )
                    break

            logger.info(
                f"Fetched {len(contributors_data)} contributors for {repo_identifier}"
            )

        except Exception as e:
            logger.error(f"Failed to fetch contributors for {repo_identifier}: {e}")
            raise

        # Fetch detailed contributor statistics
        try:
            stats_data = self.fetch_contributor_stats(repo_identifier)
            stats_by_login = {stat["login"]: stat for stat in stats_data}
        except Exception as e:
            logger.warning(
                f"Failed to fetch contributor stats for {repo_identifier}: {e}. "
                "Continuing with basic contributor data."
            )
            stats_by_login = {}

        # Parse into ContributorRecord objects
        records = []
        fetched_at = datetime.now(timezone.utc)

        for contributor in contributors_data:
            login = contributor.get("login")
            if not login:
                logger.warning(f"Contributor missing login field: {contributor}")
                continue

            contributions = contributor.get("contributions", 0)

            # Get weekly activity if available
            weeks = []
            if login in stats_by_login:
                stats = stats_by_login[login]
                weeks_data = stats.get("weeks", [])
                for week in weeks_data:
                    try:
                        weeks.append(
                            WeeklyActivity(
                                week_timestamp=week.get("w", 0),
                                additions=week.get("a", 0),
                                deletions=week.get("d", 0),
                                commits=week.get("c", 0),
                            )
                        )
                    except Exception as e:
                        logger.warning(f"Failed to parse weekly activity: {e}")
                        continue

            try:
                record = ContributorRecord(
                    login=login,
                    contributions=contributions,
                    weeks=weeks,
                    fetched_at=fetched_at,
                )
                records.append(record)
            except Exception as e:
                logger.warning(f"Failed to create ContributorRecord for {login}: {e}")
                continue

        logger.info(
            f"Parsed {len(records)} contributor records for {repo_identifier}"
        )
        return records

    def fetch_contributor_stats(self, repo_identifier: str) -> list[dict]:
        """
        Fetch detailed contributor statistics.

        Args:
            repo_identifier: Repository in owner/repo format

        Returns:
            List of contributor statistics dicts

        Raises:
            Exception: If fetching fails
        """
        logger.info(f"Fetching contributor stats for {repo_identifier}")

        # Parse repo identifier
        if "/" not in repo_identifier:
            raise ValueError(
                f"Invalid repository identifier: {repo_identifier}. "
                "Expected format: owner/repo"
            )

        owner, repo = repo_identifier.split("/", 1)

        # Fetch contributor statistics
        endpoint = f"/repos/{owner}/{repo}/stats/contributors"

        try:
            # Note: This endpoint doesn't use pagination, returns all data at once
            # It may return 202 Accepted if data is being computed
            stats_data = self.rest_client.get(endpoint)

            if isinstance(stats_data, list):
                logger.info(
                    f"Fetched stats for {len(stats_data)} contributors in {repo_identifier}"
                )
                return stats_data
            else:
                logger.warning(
                    f"Unexpected response format for {endpoint}: {type(stats_data)}"
                )
                return []

        except Exception as e:
            logger.error(f"Failed to fetch contributor stats for {repo_identifier}: {e}")
            raise
