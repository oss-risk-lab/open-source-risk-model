"""
Issues fetcher for GitHub API.

Fetches issue data using REST API endpoints with optional event enrichment.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from .models import IssueRecord
from .rest_client import RESTClient

logger = logging.getLogger(__name__)


class IssuesFetcher:
    """Fetches issue data from GitHub REST API."""

    def __init__(self, rest_client: RESTClient, config: Optional[dict] = None):
        """
        Initialize issues fetcher.

        Args:
            rest_client: REST client for API calls
            config: Optional configuration dict
        """
        self.rest_client = rest_client
        self.config = config or {}

    def fetch_issues(
        self, repo_identifier: str, state: str = "all"
    ) -> list[IssueRecord]:
        """
        Fetch issues with pagination.

        Args:
            repo_identifier: Repository in owner/repo format
            state: Issue state filter (all, open, closed)

        Returns:
            List of IssueRecord objects

        Raises:
            Exception: If fetching fails
        """
        logger.info(f"Fetching issues for {repo_identifier} with state={state}")

        # Parse repo identifier
        if "/" not in repo_identifier:
            raise ValueError(
                f"Invalid repository identifier: {repo_identifier}. "
                "Expected format: owner/repo"
            )

        owner, repo = repo_identifier.split("/", 1)

        # Fetch issues with pagination
        endpoint = f"/repos/{owner}/{repo}/issues"
        params = {"state": state, "per_page": 100}  # Max per page

        issues_data = []
        max_issues = self.config.get("max_issues_per_repo", 100)

        try:
            # Use pagination to get issues (capped at max_issues for MVP)
            max_pages = self.config.get("max_pages_per_request", 10)
            for page_data in self.rest_client.paginate(
                endpoint, params=params, max_pages=max_pages
            ):
                if isinstance(page_data, list):
                    issues_data.extend(page_data)
                    # Check if we've reached the cap
                    if len(issues_data) >= max_issues:
                        logger.info(
                            f"Reached max_issues cap ({max_issues}) for {repo_identifier}"
                        )
                        issues_data = issues_data[:max_issues]
                        break
                else:
                    logger.warning(
                        f"Unexpected response format for {endpoint}: {type(page_data)}"
                    )
                    break

            logger.info(f"Fetched {len(issues_data)} issues for {repo_identifier}")

        except Exception as e:
            logger.error(f"Failed to fetch issues for {repo_identifier}: {e}")
            raise

        # Parse into IssueRecord objects
        records = []
        fetched_at = datetime.now(timezone.utc)

        for issue in issues_data:
            # Skip pull requests (they appear in issues endpoint)
            if "pull_request" in issue:
                continue

            try:
                number = issue.get("number")
                if not number:
                    logger.warning(f"Issue missing number field: {issue}")
                    continue

                state = issue.get("state", "unknown")
                created_at_str = issue.get("created_at")
                closed_at_str = issue.get("closed_at")
                updated_at_str = issue.get("updated_at")

                # Parse timestamps
                created_at = (
                    datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                    if created_at_str
                    else datetime.now(timezone.utc)
                )
                closed_at = (
                    datetime.fromisoformat(closed_at_str.replace("Z", "+00:00"))
                    if closed_at_str
                    else None
                )
                updated_at = (
                    datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                    if updated_at_str
                    else datetime.now(timezone.utc)
                )

                comments = issue.get("comments", 0)
                author_association = issue.get("author_association", "NONE")
                labels = [label.get("name", "") for label in issue.get("labels", [])]

                record = IssueRecord(
                    number=number,
                    state=state,
                    created_at=created_at,
                    closed_at=closed_at,
                    updated_at=updated_at,
                    comments=comments,
                    author_association=author_association,
                    labels=labels,
                    fetched_at=fetched_at,
                )
                records.append(record)

            except Exception as e:
                logger.warning(f"Failed to create IssueRecord: {e}")
                continue

        logger.info(f"Parsed {len(records)} issue records for {repo_identifier}")
        return records

    def fetch_issue_events(
        self, repo_identifier: str, issue_number: int
    ) -> list[dict]:
        """
        Fetch events for specific issue (use sparingly - see guidance).

        CRITICAL: Issue events can cause API usage explosion. Use only when
        features cannot be approximated from issue metadata + comments.

        Args:
            repo_identifier: Repository in owner/repo format
            issue_number: Issue number

        Returns:
            List of issue event dicts

        Raises:
            Exception: If fetching fails
        """
        logger.info(
            f"Fetching events for issue #{issue_number} in {repo_identifier}"
        )

        # Parse repo identifier
        if "/" not in repo_identifier:
            raise ValueError(
                f"Invalid repository identifier: {repo_identifier}. "
                "Expected format: owner/repo"
            )

        owner, repo = repo_identifier.split("/", 1)

        # Fetch issue events
        endpoint = f"/repos/{owner}/{repo}/issues/{issue_number}/events"

        try:
            events_data = []
            max_pages = self.config.get("max_pages_per_request", 10)

            for page_data in self.rest_client.paginate(endpoint, max_pages=max_pages):
                if isinstance(page_data, list):
                    events_data.extend(page_data)
                else:
                    logger.warning(
                        f"Unexpected response format for {endpoint}: {type(page_data)}"
                    )
                    break

            logger.info(
                f"Fetched {len(events_data)} events for issue #{issue_number} "
                f"in {repo_identifier}"
            )
            return events_data

        except Exception as e:
            logger.error(
                f"Failed to fetch events for issue #{issue_number} "
                f"in {repo_identifier}: {e}"
            )
            raise
