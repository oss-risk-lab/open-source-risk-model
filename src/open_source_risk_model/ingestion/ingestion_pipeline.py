"""
Ingestion pipeline orchestration.

Orchestrates repository ingestion: snapshot fetch → contributors fetch → 
issues fetch → feature engineering → persistence.
"""

import logging
import time
from typing import List, Optional

from .cache_manager import CacheManager
from .config import IngestionConfig
from .contributors_fetcher import ContributorsFetcher
from .feature_engineer import FeatureEngineer
from .graphql_client import GraphQLClient
from .issues_fetcher import IssuesFetcher
from .models import IngestionResult, IngestionSummary
from .rate_limiter import RateLimiter
from .repo_snapshot_fetcher import RepoSnapshotFetcher
from .rest_client import RESTClient

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """Orchestrates repository ingestion with progress reporting."""

    def __init__(
        self,
        github_token: str,
        config: Optional[IngestionConfig] = None,
        cache_manager: Optional[CacheManager] = None,
    ):
        """
        Initialize ingestion pipeline.

        Args:
            github_token: GitHub API token
            config: Optional configuration object
            cache_manager: Optional cache manager instance
        """
        self.config = config or IngestionConfig()
        self.cache_manager = cache_manager or CacheManager(self.config)

        # Get config dict for components that expect dict
        config_dict = self.config.config if hasattr(self.config, 'config') else {}

        # Initialize rate limiter
        self.rate_limiter = RateLimiter(config_dict)

        # Initialize API clients
        self.graphql_client = GraphQLClient(
            token=github_token,
            config=config_dict,
        )

        self.rest_client = RESTClient(
            token=github_token,
            config=config_dict,
        )

        # Initialize fetchers
        self.snapshot_fetcher = RepoSnapshotFetcher(
            graphql_client=self.graphql_client, config=self.config
        )

        self.contributors_fetcher = ContributorsFetcher(
            rest_client=self.rest_client,
            config=config_dict.get("rest", {}),
        )

        self.issues_fetcher = IssuesFetcher(
            rest_client=self.rest_client,
            config=config_dict.get("ingestion", {}),
        )

        # Initialize feature engineer
        self.feature_engineer = FeatureEngineer()

        # Progress reporting interval
        self.progress_interval = self.config.get(
            "ingestion", "progress_report_interval", default=10
        )

        logger.info("Initialized IngestionPipeline")

    def ingest_repositories(
        self, repo_identifiers: List[str], mode: str = "full"
    ) -> IngestionSummary:
        """
        Ingest multiple repositories with progress reporting.

        Args:
            repo_identifiers: List of repository identifiers (owner/repo format)
            mode: Ingestion mode - "full" or "provisional"

        Returns:
            IngestionSummary with success/failure counts and API call metrics
        """
        if mode not in ["full", "provisional"]:
            raise ValueError(f"Invalid mode: {mode}. Must be 'full' or 'provisional'")

        logger.info(
            f"Starting batch ingestion of {len(repo_identifiers)} repositories "
            f"in {mode} mode"
        )

        start_time = time.time()
        results = []
        successful = 0
        failed = 0
        total_api_calls = 0

        # Process repositories
        for idx, repo_id in enumerate(repo_identifiers, 1):
            try:
                result = self.ingest_single(repo_id, mode=mode)
                results.append(result)

                if result.success:
                    successful += 1
                else:
                    failed += 1

                total_api_calls += result.api_calls_made

                # Progress reporting
                if idx % self.progress_interval == 0:
                    logger.info(
                        f"Progress: {idx}/{len(repo_identifiers)} repositories processed "
                        f"({successful} successful, {failed} failed)"
                    )

            except Exception as e:
                logger.error(f"Unexpected error ingesting {repo_id}: {e}")
                failed += 1
                results.append(
                    IngestionResult(
                        repo_full_name=repo_id,
                        success=False,
                        score_completeness=mode,
                        api_calls_made=0,
                        ingestion_time_seconds=0.0,
                        error=str(e),
                    )
                )

        # Calculate summary statistics
        total_time = time.time() - start_time
        avg_api_calls = total_api_calls / len(repo_identifiers) if repo_identifiers else 0.0
        avg_time = total_time / len(repo_identifiers) if repo_identifiers else 0.0

        # Get rate limit status
        rate_limit_remaining = {
            "rest": self.rate_limiter.get_remaining("rest"),
            "graphql": self.rate_limiter.get_remaining("graphql"),
        }

        summary = IngestionSummary(
            total_repos=len(repo_identifiers),
            successful=successful,
            failed=failed,
            total_api_calls=total_api_calls,
            total_time_seconds=total_time,
            avg_api_calls_per_repo=avg_api_calls,
            avg_time_per_repo=avg_time,
            rate_limit_remaining=rate_limit_remaining,
        )

        logger.info(
            f"Batch ingestion complete: {successful}/{len(repo_identifiers)} successful, "
            f"{failed} failed, {total_api_calls} API calls, {total_time:.2f}s total"
        )

        return summary

    def ingest_single(self, repo_identifier: str, mode: str = "full") -> IngestionResult:
        """
        Ingest single repository.

        Args:
            repo_identifier: Repository identifier (owner/repo format)
            mode: Ingestion mode - "full" or "provisional"

        Returns:
            IngestionResult with features, score, completeness, API calls, timing
        """
        if mode not in ["full", "provisional"]:
            raise ValueError(f"Invalid mode: {mode}. Must be 'full' or 'provisional'")

        logger.info(f"Ingesting {repo_identifier} in {mode} mode")

        start_time = time.time()
        api_calls_made = 0

        try:
            # Step 1: Fetch repository snapshot
            logger.debug(f"Fetching snapshot for {repo_identifier}")
            snapshot = self.snapshot_fetcher.fetch_single(repo_identifier)
            api_calls_made += 1  # GraphQL query

            # Step 2: Fetch contributors
            logger.debug(f"Fetching contributors for {repo_identifier}")
            contributors = self.contributors_fetcher.fetch_contributors(repo_identifier)
            api_calls_made += 2  # Contributors list + stats

            # Step 3: Fetch issues (only in full mode)
            issues = []
            if mode == "full":
                logger.debug(f"Fetching issues for {repo_identifier}")
                issues = self.issues_fetcher.fetch_issues(repo_identifier)
                api_calls_made += 1  # Issues list

            # Step 4: Feature engineering
            logger.debug(f"Computing features for {repo_identifier}")
            if mode == "provisional":
                features = self.feature_engineer.compute_provisional_features(
                    snapshot, contributors
                )
            else:
                features = self.feature_engineer.compute_features(
                    snapshot, contributors, issues
                )

            # Step 5: Check feature coverage
            coverage, missing_categories = self.feature_engineer.check_feature_coverage(
                features
            )

            # Get minimum coverage threshold
            min_coverage = self.config.get(
                "features", "minimum_coverage_threshold", default=0.6
            )

            # Check if coverage meets threshold
            if coverage < min_coverage:
                error_msg = (
                    f"Feature coverage {coverage:.2%} below minimum threshold "
                    f"{min_coverage:.2%}. Missing categories: {missing_categories}"
                )
                logger.warning(f"{repo_identifier}: {error_msg}")

                ingestion_time = time.time() - start_time

                return IngestionResult(
                    repo_full_name=repo_identifier,
                    success=False,
                    score_completeness=mode,
                    api_calls_made=api_calls_made,
                    ingestion_time_seconds=ingestion_time,
                    error=error_msg,
                    missing_feature_categories=missing_categories,
                )

            # Step 6: Compute maintenance risk score
            # For now, we'll use a simple weighted average
            # In production, this would use the full scoring logic
            score = self._compute_risk_score(features)

            ingestion_time = time.time() - start_time

            logger.info(
                f"Successfully ingested {repo_identifier}: score={score:.3f}, "
                f"coverage={coverage:.2%}, {api_calls_made} API calls, "
                f"{ingestion_time:.2f}s"
            )

            return IngestionResult(
                repo_full_name=repo_identifier,
                success=True,
                features=features,
                maintenance_risk_score=score,
                score_completeness=mode,
                api_calls_made=api_calls_made,
                ingestion_time_seconds=ingestion_time,
                missing_feature_categories=missing_categories,
            )

        except Exception as e:
            ingestion_time = time.time() - start_time
            error_msg = str(e)
            logger.error(f"Failed to ingest {repo_identifier}: {error_msg}")

            return IngestionResult(
                repo_full_name=repo_identifier,
                success=False,
                score_completeness=mode,
                api_calls_made=api_calls_made,
                ingestion_time_seconds=ingestion_time,
                error=error_msg,
            )

    def _compute_risk_score(self, features: dict[str, float]) -> float:
        """
        Compute maintenance risk score from features.

        Args:
            features: Dictionary of feature values

        Returns:
            Risk score between 0.0 and 1.0
        """
        # Get feature weights from config
        weights = self.feature_engineer.feature_weights

        # Compute weighted average
        total_weight = 0.0
        weighted_sum = 0.0

        for feature_name, weight in weights.items():
            if feature_name in features and features[feature_name] is not None:
                # Normalize feature value to 0-1 range if needed
                value = features[feature_name]

                # Apply weight
                weighted_sum += value * weight
                total_weight += weight

        # Calculate final score
        if total_weight > 0:
            score = weighted_sum / total_weight
        else:
            score = 0.5  # Default to medium risk if no features available

        # Ensure score is in valid range
        score = max(0.0, min(1.0, score))

        return score
