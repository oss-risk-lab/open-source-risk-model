"""
Result summarizer for combining and formatting query results.

Combines database and live ingestion results, generates natural language
responses, and provides warnings about data quality and comparisons.
"""

from typing import Any

from ..ingestion.models import EvidenceScope
from .models import QueryResponse, RepoSummary


class ResultSummarizer:
    """Combine and format query results."""

    def merge_results(
        self,
        db_results: list[RepoSummary],
        live_results: list[RepoSummary],
    ) -> list[RepoSummary]:
        """
        Merge database and live ingestion results.

        Preserves DataProvenance for each repository and identifies
        which repos came from database vs live ingestion.

        Args:
            db_results: Results from database retrieval
            live_results: Results from live ingestion

        Returns:
            Combined list of RepoSummary objects
        """
        # Combine results, avoiding duplicates
        seen_repos = set()
        merged = []

        for result in db_results:
            if result.repo_full_name not in seen_repos:
                merged.append(result)
                seen_repos.add(result.repo_full_name)

        for result in live_results:
            if result.repo_full_name not in seen_repos:
                merged.append(result)
                seen_repos.add(result.repo_full_name)

        return merged

    def summarize(
        self,
        results: list[RepoSummary],
        intent: str,
        evidence_scope: EvidenceScope,
    ) -> QueryResponse:
        """
        Generate natural language response from results.

        Ranks repositories by maintenance_risk_score, explains key
        contributing factors, includes data provenance information,
        and warns about provisional scores or mixed comparisons.

        Args:
            results: List of repository summaries
            intent: Query intent (repo_lookup, repo_comparison, etc.)
            evidence_scope: Evidence scope tracking

        Returns:
            QueryResponse with natural language response and metadata
        """
        if not results:
            return QueryResponse(
                natural_language_response="No repositories found matching your query.",
                structured_results=[],
                warnings=["No results found"],
                metadata={"intent": intent, "result_count": 0},
                evidence_scope=evidence_scope,
            )

        # Sort by maintenance risk score (ascending = lower risk first)
        sorted_results = sorted(results, key=lambda r: r.maintenance_risk_score)

        # Generate natural language response
        nl_response = self._generate_natural_language(sorted_results, intent)

        # Generate warnings
        warnings = self._generate_warnings(sorted_results)

        # Generate metadata
        metadata = self._generate_metadata(sorted_results, intent)

        return QueryResponse(
            natural_language_response=nl_response,
            structured_results=sorted_results,
            warnings=warnings,
            metadata=metadata,
            evidence_scope=evidence_scope,
        )

    def _generate_natural_language(
        self, results: list[RepoSummary], intent: str
    ) -> str:
        """
        Generate natural language response.

        Args:
            results: Sorted list of repository summaries
            intent: Query intent

        Returns:
            Natural language response string
        """
        if len(results) == 1:
            return self._generate_single_repo_response(results[0])
        else:
            return self._generate_multi_repo_response(results, intent)

    def _generate_single_repo_response(self, repo: RepoSummary) -> str:
        """Generate response for single repository."""
        lines = []

        # Repository name and risk band
        lines.append(
            f"{repo.repo_full_name} has a {repo.risk_band} maintenance risk "
            f"(score: {repo.maintenance_risk_score:.2f})."
        )

        # Key contributing factors
        factors = self._identify_key_factors(repo)
        if factors:
            lines.append("\nKey factors:")
            for factor in factors:
                lines.append(f"  • {factor}")

        # Data provenance
        provenance_info = self._format_provenance(repo)
        lines.append(f"\n{provenance_info}")

        return "\n".join(lines)

    def _generate_multi_repo_response(
        self, results: list[RepoSummary], intent: str
    ) -> str:
        """Generate response for multiple repositories."""
        lines = []

        # Summary line
        lines.append(f"Analyzed {len(results)} repositories:")

        # List repositories with risk bands
        for i, repo in enumerate(results[:10], 1):  # Limit to top 10
            lines.append(
                f"  {i}. {repo.repo_full_name}: {repo.risk_band} risk "
                f"({repo.maintenance_risk_score:.2f})"
            )

        if len(results) > 10:
            lines.append(f"  ... and {len(results) - 10} more")

        # Highlight best and worst
        best = results[0]
        worst = results[-1]
        lines.append(
            f"\nLowest risk: {best.repo_full_name} ({best.risk_band}, {best.maintenance_risk_score:.2f})"
        )
        lines.append(
            f"Highest risk: {worst.repo_full_name} ({worst.risk_band}, {worst.maintenance_risk_score:.2f})"
        )

        return "\n".join(lines)

    def _identify_key_factors(self, repo: RepoSummary) -> list[str]:
        """
        Identify key contributing factors to risk score.

        Args:
            repo: Repository summary

        Returns:
            List of factor descriptions
        """
        factors = []
        features = repo.features

        # Check for high-impact factors
        if "days_since_last_push" in features:
            days = features["days_since_last_push"]
            if days > 180:
                factors.append(f"No activity in {int(days)} days")
            elif days > 90:
                factors.append(f"Limited recent activity ({int(days)} days since last push)")

        if "fraction_open_issues_stale_180d" in features:
            stale_fraction = features["fraction_open_issues_stale_180d"]
            if stale_fraction > 0.5:
                factors.append(f"{int(stale_fraction * 100)}% of open issues are stale")

        if "contributors_last_12mo" in features:
            contributors = features["contributors_last_12mo"]
            if contributors < 3:
                factors.append(f"Only {int(contributors)} active contributors")

        if "fraction_issues_closed_12mo" in features:
            closed_fraction = features["fraction_issues_closed_12mo"]
            if closed_fraction < 0.3:
                factors.append(f"Low issue closure rate ({int(closed_fraction * 100)}%)")

        return factors[:3]  # Limit to top 3 factors

    def _format_provenance(self, repo: RepoSummary) -> str:
        """Format provenance information."""
        prov = repo.provenance
        source_str = "database" if prov.source == "database" else "live ingestion"
        completeness_str = (
            "full analysis" if prov.score_completeness == "full" else "provisional analysis"
        )

        parts = [f"Data source: {source_str} ({completeness_str})"]

        if prov.missing_feature_categories:
            parts.append(
                f"Note: Missing {', '.join(prov.missing_feature_categories)} data"
            )

        return " | ".join(parts)

    def _generate_warnings(self, results: list[RepoSummary]) -> list[str]:
        """
        Generate warnings about data quality and comparisons.

        Args:
            results: List of repository summaries

        Returns:
            List of warning messages
        """
        warnings = []

        # Check for mixed score completeness
        completeness_types = {r.provenance.score_completeness for r in results}
        if len(completeness_types) > 1:
            warnings.append(
                "Results include both provisional and full scores. "
                "Direct comparisons may not be accurate."
            )

        # Check for provisional scores
        provisional_count = sum(
            1 for r in results if r.provenance.score_completeness == "provisional"
        )
        if provisional_count > 0:
            warnings.append(
                f"{provisional_count} repository(ies) have provisional scores "
                "(based on limited data). Consider requesting full analysis."
            )

        # Check for missing feature categories
        repos_with_missing = [
            r for r in results if r.provenance.missing_feature_categories
        ]
        if repos_with_missing:
            warnings.append(
                f"{len(repos_with_missing)} repository(ies) have incomplete feature data."
            )

        return warnings

    def _generate_metadata(
        self, results: list[RepoSummary], intent: str
    ) -> dict[str, Any]:
        """
        Generate metadata about results.

        Args:
            results: List of repository summaries
            intent: Query intent

        Returns:
            Metadata dictionary
        """
        metadata = {
            "intent": intent,
            "result_count": len(results),
            "risk_band_distribution": self._calculate_risk_distribution(results),
            "data_sources": self._summarize_data_sources(results),
        }

        return metadata

    def _calculate_risk_distribution(
        self, results: list[RepoSummary]
    ) -> dict[str, int]:
        """Calculate distribution of risk bands."""
        distribution = {"low": 0, "medium": 0, "high": 0, "critical": 0}

        for result in results:
            if result.risk_band in distribution:
                distribution[result.risk_band] += 1

        return distribution

    def _summarize_data_sources(self, results: list[RepoSummary]) -> dict[str, int]:
        """Summarize data sources used."""
        sources = {"database": 0, "live_fetch": 0}

        for result in results:
            source = result.provenance.source
            if source in sources:
                sources[source] += 1

        return sources
