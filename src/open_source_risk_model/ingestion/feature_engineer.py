"""
Feature engineering for maintenance risk scoring.

Computes derived maintenance risk metrics from raw GitHub data with weighted
feature coverage tracking.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from src.open_source_risk_model.config.feature_mapping_config import (
    get_composite_config,
)
from src.open_source_risk_model.ingestion.models import (
    ContributorRecord,
    IssueRecord,
    RepositorySnapshot,
)


class FeatureEngineer:
    """
    Computes derived maintenance risk metrics from raw GitHub data.
    
    Supports both full feature computation (all features) and provisional
    feature computation (snapshot + contributor features only).
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize feature engineer.
        
        Args:
            config: Optional configuration dict. If None, loads from composite_config.yaml
        """
        self.config = config or get_composite_config()
        self.feature_weights = self.config.get("maintenance_composite", {}).get(
            "feature_weights", {}
        )

    def compute_features(
        self,
        snapshot: RepositorySnapshot,
        contributors: List[ContributorRecord],
        issues: List[IssueRecord],
    ) -> Dict[str, float]:
        """
        Compute all features from raw data.
        
        Args:
            snapshot: Repository snapshot data
            contributors: List of contributor records
            issues: List of issue records
            
        Returns:
            Dictionary of feature names to values
        """
        features = {}
        
        # Snapshot features
        features.update(self._compute_snapshot_features(snapshot))
        
        # Contributor features
        features.update(self._compute_contributor_features(contributors))
        
        # Issue lifecycle features
        features.update(self._compute_issue_features(issues, contributors))
        
        return features

    def compute_provisional_features(
        self,
        snapshot: RepositorySnapshot,
        contributors: List[ContributorRecord],
    ) -> Dict[str, float]:
        """
        Compute snapshot-only features (fast mode).
        
        Args:
            snapshot: Repository snapshot data
            contributors: List of contributor records
            
        Returns:
            Dictionary of feature names to values (subset of full features)
        """
        features = {}
        
        # Snapshot features
        features.update(self._compute_snapshot_features(snapshot))
        
        # Contributor features
        features.update(self._compute_contributor_features(contributors))
        
        return features

    def check_feature_coverage(
        self,
        features: Dict[str, float],
        weights: Optional[Dict[str, float]] = None,
    ) -> Tuple[float, List[str]]:
        """
        Check WEIGHTED feature coverage and identify missing categories.
        
        Args:
            features: Dictionary of computed features
            weights: Optional feature weights. If None, uses config weights.
            
        Returns:
            Tuple of (coverage_percentage, missing_categories)
            - coverage_percentage: 0.0 to 1.0 representing weighted coverage
            - missing_categories: List of missing feature category names
        """
        if weights is None:
            weights = self.feature_weights
        
        # Calculate weighted coverage
        total_weight = 0.0
        available_weight = 0.0
        
        for feature_name, weight in weights.items():
            total_weight += weight
            if feature_name in features and features[feature_name] is not None:
                available_weight += weight
        
        coverage = available_weight / total_weight if total_weight > 0 else 0.0
        
        # Identify missing feature categories
        missing_categories = self._identify_missing_categories(features, weights)
        
        return coverage, missing_categories

    def _compute_snapshot_features(
        self, snapshot: RepositorySnapshot
    ) -> Dict[str, float]:
        """Compute features from repository snapshot."""
        features = {}
        # Use snapshot.fetched_at for deterministic calculations
        now = snapshot.fetched_at
        
        # days_since_last_push
        if snapshot.pushed_at:
            delta = now - snapshot.pushed_at
            features["days_since_last_push"] = delta.total_seconds() / 86400.0
        
        # days_since_last_release
        if snapshot.latest_release:
            delta = now - snapshot.latest_release
            features["days_since_last_release"] = delta.total_seconds() / 86400.0
        else:
            # No release means very high risk
            features["days_since_last_release"] = 730.0  # 2 years default
        
        # stars_count
        features["stars_count"] = float(snapshot.stargazer_count)
        
        # archived (0.0 for not archived, 1.0 for archived)
        features["archived"] = 1.0 if snapshot.is_archived else 0.0
        
        # open_issues_count - only include if it's in the weights config
        if "open_issues_count" in self.feature_weights:
            features["open_issues_count"] = float(snapshot.open_issues_count)
        
        return features

    def _compute_contributor_features(
        self, contributors: List[ContributorRecord]
    ) -> Dict[str, float]:
        """Compute features from contributor data."""
        features = {}
        
        # contributors_count
        features["contributors_count"] = float(len(contributors))
        
        if not contributors:
            # No contributors means high risk
            features["contributors_last_12mo"] = 0.0
            features["top_contributor_fraction_12mo"] = 1.0
            return features
        
        # Calculate 12-month activity using fetched_at from first contributor for determinism
        now = contributors[0].fetched_at
        twelve_months_ago = now.timestamp() - (365 * 86400)
        
        active_contributors_12mo = 0
        contributor_commits_12mo = []
        
        for contributor in contributors:
            commits_12mo = 0
            for week in contributor.weeks:
                if week.week_timestamp >= twelve_months_ago:
                    commits_12mo += week.commits
            
            if commits_12mo > 0:
                active_contributors_12mo += 1
                contributor_commits_12mo.append(commits_12mo)
        
        # contributors_last_12mo
        features["contributors_last_12mo"] = float(active_contributors_12mo)
        
        # top_contributor_fraction_12mo
        if contributor_commits_12mo:
            total_commits = sum(contributor_commits_12mo)
            max_commits = max(contributor_commits_12mo)
            features["top_contributor_fraction_12mo"] = (
                max_commits / total_commits if total_commits > 0 else 1.0
            )
        else:
            features["top_contributor_fraction_12mo"] = 1.0
        
        return features

    def _compute_issue_features(
        self,
        issues: List[IssueRecord],
        contributors: List[ContributorRecord],
    ) -> Dict[str, float]:
        """Compute features from issue lifecycle data."""
        features = {}
        
        if not issues:
            # No issues data - return None for issue features
            return {
                "issues_per_contributor": None,
                "fraction_issues_closed_12mo": None,
                "fraction_open_issues_stale_180d": None,
                "avg_time_to_first_maintainer_response_days": None,
                "median_time_to_close_days": None,
                "open_issue_age_p90_days": None,
            }
        
        # Use the fetched_at timestamp from the first issue for deterministic calculations
        now = issues[0].fetched_at
        twelve_months_ago = now - timedelta(days=365)
        six_months_ago = now - timedelta(days=180)
        
        # issues_per_contributor
        contributor_count = len(contributors) if contributors else 1
        features["issues_per_contributor"] = len(issues) / contributor_count
        
        # Filter issues by time period
        issues_12mo = [i for i in issues if i.created_at >= twelve_months_ago]
        open_issues = [i for i in issues if i.state == "open"]
        
        # fraction_issues_closed_12mo
        if issues_12mo:
            closed_12mo = [i for i in issues_12mo if i.state == "closed"]
            features["fraction_issues_closed_12mo"] = len(closed_12mo) / len(issues_12mo)
        else:
            features["fraction_issues_closed_12mo"] = 0.0
        
        # fraction_open_issues_stale_180d
        if open_issues:
            stale_issues = [i for i in open_issues if i.updated_at < six_months_ago]
            features["fraction_open_issues_stale_180d"] = len(stale_issues) / len(
                open_issues
            )
        else:
            features["fraction_open_issues_stale_180d"] = 0.0
        
        # avg_time_to_first_maintainer_response_days
        # For MVP, we approximate this using comment count as a proxy
        # Issues with comments likely have maintainer responses
        issues_with_comments = [i for i in issues if i.comments > 0]
        if issues_with_comments:
            # Approximate: assume first comment happens within 1 day for active repos
            # This is a simplification - full implementation would need issue events
            features["avg_time_to_first_maintainer_response_days"] = 1.0
        else:
            # No comments suggests no maintainer response
            features["avg_time_to_first_maintainer_response_days"] = 30.0
        
        # median_time_to_close_days
        closed_issues = [i for i in issues if i.state == "closed" and i.closed_at]
        if closed_issues:
            close_times = []
            for issue in closed_issues:
                delta = issue.closed_at - issue.created_at
                close_times.append(delta.total_seconds() / 86400.0)
            
            close_times.sort()
            median_idx = len(close_times) // 2
            features["median_time_to_close_days"] = close_times[median_idx]
        else:
            features["median_time_to_close_days"] = 365.0  # Default high value
        
        # open_issue_age_p90_days
        if open_issues:
            ages = []
            for issue in open_issues:
                delta = now - issue.created_at
                ages.append(delta.total_seconds() / 86400.0)
            
            ages.sort()
            p90_idx = int(len(ages) * 0.9)
            features["open_issue_age_p90_days"] = ages[p90_idx]
        else:
            features["open_issue_age_p90_days"] = 0.0
        
        return features

    def _identify_missing_categories(
        self, features: Dict[str, float], weights: Dict[str, float]
    ) -> List[str]:
        """
        Identify which feature CATEGORIES are missing.
        
        Returns list of category names: "snapshot_metrics", "contributor_metrics",
        "issue_lifecycle_metrics"
        """
        missing_categories = []
        
        # Define feature categories
        snapshot_features = {
            "days_since_last_push",
            "days_since_last_release",
            "stars_count",
            "archived",
        }
        
        contributor_features = {
            "contributors_count",
            "contributors_last_12mo",
            "top_contributor_fraction_12mo",
        }
        
        issue_features = {
            "issues_per_contributor",
            "fraction_issues_closed_12mo",
            "fraction_open_issues_stale_180d",
            "avg_time_to_first_maintainer_response_days",
            "median_time_to_close_days",
            "open_issue_age_p90_days",
        }
        
        # Check if any features in each category are missing
        def category_missing(category_features):
            """Check if any weighted features in category are missing."""
            for feature in category_features:
                if feature in weights and weights[feature] > 0:
                    if feature not in features or features[feature] is None:
                        return True
            return False
        
        if category_missing(snapshot_features):
            missing_categories.append("snapshot_metrics")
        
        if category_missing(contributor_features):
            missing_categories.append("contributor_metrics")
        
        if category_missing(issue_features):
            missing_categories.append("issue_lifecycle_metrics")
        
        return missing_categories
