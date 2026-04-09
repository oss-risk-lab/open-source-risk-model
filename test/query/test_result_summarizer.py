"""
Unit tests for ResultSummarizer.

Tests result merging, natural language generation, and warning generation.
"""

from datetime import datetime, timezone

import pytest

from src.open_source_risk_model.ingestion.models import DataProvenance, EvidenceScope
from src.open_source_risk_model.query.models import RepoSummary
from src.open_source_risk_model.query.result_summarizer import ResultSummarizer


@pytest.fixture
def evidence_scope():
    """Create sample evidence scope."""
    return EvidenceScope(
        source_level="scored_features",
        includes_live_fetch=False,
        includes_cached_results=False,
        includes_database_results=True,
    )


@pytest.fixture
def sample_repo_low_risk():
    """Create sample repository with low risk."""
    return RepoSummary(
        repo_full_name="numpy/numpy",
        maintenance_risk_score=0.15,
        risk_band="low",
        features={
            "days_since_last_push": 5.0,
            "stars_count": 25000.0,
            "contributors_last_12mo": 50.0,
            "fraction_issues_closed_12mo": 0.8,
        },
        provenance=DataProvenance(
            source="database",
            last_updated=datetime.now(timezone.utc),
            score_completeness="full",
        ),
    )


@pytest.fixture
def sample_repo_high_risk():
    """Create sample repository with high risk."""
    return RepoSummary(
        repo_full_name="abandoned/project",
        maintenance_risk_score=0.75,
        risk_band="high",
        features={
            "days_since_last_push": 365.0,
            "stars_count": 100.0,
            "contributors_last_12mo": 1.0,
            "fraction_open_issues_stale_180d": 0.9,
            "fraction_issues_closed_12mo": 0.1,
        },
        provenance=DataProvenance(
            source="live_fetch",
            last_updated=datetime.now(timezone.utc),
            score_completeness="provisional",
            missing_feature_categories=["issue_lifecycle"],
        ),
    )


def test_merge_results_no_duplicates(sample_repo_low_risk, sample_repo_high_risk):
    """Test merging results without duplicates."""
    summarizer = ResultSummarizer()

    db_results = [sample_repo_low_risk]
    live_results = [sample_repo_high_risk]

    merged = summarizer.merge_results(db_results, live_results)

    assert len(merged) == 2
    repo_names = {r.repo_full_name for r in merged}
    assert repo_names == {"numpy/numpy", "abandoned/project"}


def test_merge_results_with_duplicates(sample_repo_low_risk):
    """Test merging results with duplicates (database takes precedence)."""
    summarizer = ResultSummarizer()

    # Same repo in both lists
    db_results = [sample_repo_low_risk]
    live_results = [sample_repo_low_risk]

    merged = summarizer.merge_results(db_results, live_results)

    assert len(merged) == 1
    assert merged[0].repo_full_name == "numpy/numpy"


def test_merge_results_empty_lists():
    """Test merging empty result lists."""
    summarizer = ResultSummarizer()

    merged = summarizer.merge_results([], [])

    assert len(merged) == 0


def test_summarize_single_repo(sample_repo_low_risk, evidence_scope):
    """Test summarizing single repository."""
    summarizer = ResultSummarizer()

    response = summarizer.summarize([sample_repo_low_risk], "repo_lookup", evidence_scope)

    assert "numpy/numpy" in response.natural_language_response
    assert "low" in response.natural_language_response
    assert "0.15" in response.natural_language_response
    assert len(response.structured_results) == 1
    assert response.metadata["result_count"] == 1


def test_summarize_multiple_repos(
    sample_repo_low_risk, sample_repo_high_risk, evidence_scope
):
    """Test summarizing multiple repositories."""
    summarizer = ResultSummarizer()

    results = [sample_repo_low_risk, sample_repo_high_risk]
    response = summarizer.summarize(results, "repo_comparison", evidence_scope)

    assert "Analyzed 2 repositories" in response.natural_language_response
    assert "numpy/numpy" in response.natural_language_response
    assert "abandoned/project" in response.natural_language_response
    assert len(response.structured_results) == 2


def test_summarize_empty_results(evidence_scope):
    """Test summarizing empty results."""
    summarizer = ResultSummarizer()

    response = summarizer.summarize([], "repo_lookup", evidence_scope)

    assert "No repositories found" in response.natural_language_response
    assert len(response.structured_results) == 0
    assert "No results found" in response.warnings


def test_results_sorted_by_risk(
    sample_repo_low_risk, sample_repo_high_risk, evidence_scope
):
    """Test that results are sorted by risk score."""
    summarizer = ResultSummarizer()

    # Pass in reverse order (high risk first)
    results = [sample_repo_high_risk, sample_repo_low_risk]
    response = summarizer.summarize(results, "repo_comparison", evidence_scope)

    # Should be sorted with low risk first
    assert response.structured_results[0].repo_full_name == "numpy/numpy"
    assert response.structured_results[1].repo_full_name == "abandoned/project"


def test_warning_for_mixed_completeness(
    sample_repo_low_risk, sample_repo_high_risk, evidence_scope
):
    """Test warning generated for mixed score completeness."""
    summarizer = ResultSummarizer()

    # One full, one provisional
    results = [sample_repo_low_risk, sample_repo_high_risk]
    response = summarizer.summarize(results, "repo_comparison", evidence_scope)

    assert any("provisional and full scores" in w for w in response.warnings)


def test_warning_for_provisional_scores(sample_repo_high_risk, evidence_scope):
    """Test warning generated for provisional scores."""
    summarizer = ResultSummarizer()

    results = [sample_repo_high_risk]
    response = summarizer.summarize(results, "repo_lookup", evidence_scope)

    assert any("provisional scores" in w for w in response.warnings)


def test_warning_for_missing_features(sample_repo_high_risk, evidence_scope):
    """Test warning generated for missing feature categories."""
    summarizer = ResultSummarizer()

    results = [sample_repo_high_risk]
    response = summarizer.summarize(results, "repo_lookup", evidence_scope)

    assert any("incomplete feature data" in w for w in response.warnings)


def test_metadata_includes_risk_distribution(
    sample_repo_low_risk, sample_repo_high_risk, evidence_scope
):
    """Test metadata includes risk band distribution."""
    summarizer = ResultSummarizer()

    results = [sample_repo_low_risk, sample_repo_high_risk]
    response = summarizer.summarize(results, "repo_comparison", evidence_scope)

    distribution = response.metadata["risk_band_distribution"]
    assert distribution["low"] == 1
    assert distribution["high"] == 1
    assert distribution["medium"] == 0
    assert distribution["critical"] == 0


def test_metadata_includes_data_sources(
    sample_repo_low_risk, sample_repo_high_risk, evidence_scope
):
    """Test metadata includes data source summary."""
    summarizer = ResultSummarizer()

    results = [sample_repo_low_risk, sample_repo_high_risk]
    response = summarizer.summarize(results, "repo_comparison", evidence_scope)

    sources = response.metadata["data_sources"]
    assert sources["database"] == 1
    assert sources["live_fetch"] == 1


def test_key_factors_identified(sample_repo_high_risk, evidence_scope):
    """Test that key risk factors are identified."""
    summarizer = ResultSummarizer()

    response = summarizer.summarize([sample_repo_high_risk], "repo_lookup", evidence_scope)

    # Should mention high-impact factors
    nl_response = response.natural_language_response
    assert "365 days" in nl_response or "No activity" in nl_response


def test_provenance_included_in_response(sample_repo_low_risk, evidence_scope):
    """Test that provenance information is included."""
    summarizer = ResultSummarizer()

    response = summarizer.summarize([sample_repo_low_risk], "repo_lookup", evidence_scope)

    assert "database" in response.natural_language_response
    assert "full analysis" in response.natural_language_response


def test_best_and_worst_highlighted(
    sample_repo_low_risk, sample_repo_high_risk, evidence_scope
):
    """Test that best and worst repos are highlighted in multi-repo response."""
    summarizer = ResultSummarizer()

    results = [sample_repo_low_risk, sample_repo_high_risk]
    response = summarizer.summarize(results, "repo_comparison", evidence_scope)

    assert "Lowest risk: numpy/numpy" in response.natural_language_response
    assert "Highest risk: abandoned/project" in response.natural_language_response


def test_large_result_set_truncated(evidence_scope):
    """Test that large result sets are truncated in response."""
    summarizer = ResultSummarizer()

    # Create 15 repos
    results = []
    for i in range(15):
        results.append(
            RepoSummary(
                repo_full_name=f"org/repo{i}",
                maintenance_risk_score=0.1 + i * 0.05,
                risk_band="low",
                features={},
                provenance=DataProvenance(
                    source="database",
                    last_updated=datetime.now(timezone.utc),
                    score_completeness="full",
                ),
            )
        )

    response = summarizer.summarize(results, "search_ranking", evidence_scope)

    # Should show top 10 and mention "and 5 more"
    assert "and 5 more" in response.natural_language_response


def test_evidence_scope_preserved(sample_repo_low_risk, evidence_scope):
    """Test that evidence scope is preserved in response."""
    summarizer = ResultSummarizer()

    response = summarizer.summarize([sample_repo_low_risk], "repo_lookup", evidence_scope)

    assert response.evidence_scope == evidence_scope
    assert response.evidence_scope.includes_database_results is True
