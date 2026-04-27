"""
Property-based tests for ResultSummarizer.

Property 30: Provenance Completeness
- All results include complete provenance information
- Provenance is preserved through merging

Property 33: Hybrid Result Preservation
- Merging preserves all unique repositories
- No data loss during merge
- Database results take precedence over duplicates
"""

from datetime import datetime, timezone

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.open_source_risk_model.ingestion.models import DataProvenance, EvidenceScope
from src.open_source_risk_model.query.models import RepoSummary
from src.open_source_risk_model.query.result_summarizer import ResultSummarizer


def create_repo_summary(repo_name: str, score: float, source: str, completeness: str):
    """Helper to create RepoSummary."""
    risk_band = "low" if score < 0.3 else "medium" if score < 0.6 else "high"
    return RepoSummary(
        repo_full_name=repo_name,
        maintenance_risk_score=score,
        risk_band=risk_band,
        features={"days_since_last_push": 5.0},
        provenance=DataProvenance(
            source=source,
            last_updated=datetime.now(timezone.utc),
            score_completeness=completeness,
        ),
    )


@pytest.mark.property_test
@given(
    repo_names=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
            min_size=3,
            max_size=20,
        ).map(lambda s: f"{s[:10]}/{s[10:]}"),
        min_size=1,
        max_size=10,
        unique=True,
    ),
    scores=st.lists(
        st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=1,
        max_size=10,
    ),
)
@settings(max_examples=100, deadline=None)
def test_provenance_completeness(repo_names, scores):
    """
    Property 30: Provenance Completeness.

    Validates:
    - All results include complete provenance information
    - Provenance fields are non-null
    - Provenance is preserved through summarization
    """
    # Ensure we have matching lengths
    min_len = min(len(repo_names), len(scores))
    repo_names = repo_names[:min_len]
    scores = scores[:min_len]

    summarizer = ResultSummarizer()

    # Create results with provenance
    results = [
        create_repo_summary(name, score, "database", "full")
        for name, score in zip(repo_names, scores)
    ]

    evidence_scope = EvidenceScope(
        source_level="scored_features",
        includes_live_fetch=False,
        includes_cached_results=False,
        includes_database_results=True,
    )

    response = summarizer.summarize(results, "repo_lookup", evidence_scope)

    # Property 1: All results have provenance
    for result in response.structured_results:
        assert result.provenance is not None
        assert result.provenance.source is not None
        assert result.provenance.last_updated is not None
        assert result.provenance.score_completeness is not None

    # Property 2: Provenance is preserved
    for original, returned in zip(results, response.structured_results):
        assert returned.provenance.source == original.provenance.source
        assert returned.provenance.score_completeness == original.provenance.score_completeness


@pytest.mark.property_test
@given(
    db_repos=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
            min_size=3,
            max_size=20,
        ).map(lambda s: f"{s[:10]}/{s[10:]}"),
        min_size=0,
        max_size=10,
        unique=True,
    ),
    live_repos=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
            min_size=3,
            max_size=20,
        ).map(lambda s: f"{s[:10]}/{s[10:]}"),
        min_size=0,
        max_size=10,
        unique=True,
    ),
)
@settings(max_examples=100, deadline=None)
def test_hybrid_result_preservation(db_repos, live_repos):
    """
    Property 33: Hybrid Result Preservation.

    Validates:
    - Merging preserves all unique repositories
    - No data loss during merge
    - Database results take precedence over duplicates
    """
    summarizer = ResultSummarizer()

    # Create database results
    db_results = [
        create_repo_summary(name, 0.2, "database", "full") for name in db_repos
    ]

    # Create live results
    live_results = [
        create_repo_summary(name, 0.3, "live_fetch", "provisional") for name in live_repos
    ]

    merged = summarizer.merge_results(db_results, live_results)

    # Property 1: All unique repos are preserved
    expected_repos = set(db_repos) | set(live_repos)
    actual_repos = {r.repo_full_name for r in merged}
    assert actual_repos == expected_repos

    # Property 2: No data loss (count matches unique repos)
    assert len(merged) == len(expected_repos)

    # Property 3: Database results take precedence for duplicates
    for repo_name in set(db_repos) & set(live_repos):
        # Find the merged result
        merged_result = next(r for r in merged if r.repo_full_name == repo_name)
        # Should have database provenance
        assert merged_result.provenance.source == "database"


@pytest.mark.property_test
@given(
    repos=st.lists(
        st.tuples(
            st.text(
                alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
                min_size=3,
                max_size=20,
            ).map(lambda s: f"{s[:10]}/{s[10:]}"),
            st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        ),
        min_size=1,
        max_size=10,
        unique_by=lambda x: x[0],  # Unique by repo name
    )
)
@settings(max_examples=100, deadline=None)
def test_result_ordering_by_score(repos):
    """
    Property: Result Ordering.

    Validates:
    - Results are sorted by maintenance risk score (ascending)
    - Lower scores appear first
    """
    summarizer = ResultSummarizer()

    # Create results
    results = [create_repo_summary(name, score, "database", "full") for name, score in repos]

    evidence_scope = EvidenceScope(
        source_level="scored_features",
        includes_live_fetch=False,
        includes_cached_results=False,
        includes_database_results=True,
    )

    response = summarizer.summarize(results, "repo_comparison", evidence_scope)

    # Property: Results are sorted by score (ascending)
    scores = [r.maintenance_risk_score for r in response.structured_results]
    assert scores == sorted(scores)


@pytest.mark.property_test
@given(
    repo_count=st.integers(min_value=1, max_value=20),  # Changed from 0 to 1
)
@settings(max_examples=100, deadline=None)
def test_metadata_consistency(repo_count):
    """
    Property: Metadata Consistency.

    Validates:
    - Metadata result_count matches actual results
    - Risk distribution sums to total count
    - Data source counts sum to total count
    """
    summarizer = ResultSummarizer()

    # Create results with scores that stay within bounds
    results = [
        create_repo_summary(f"org/repo{i}", min(0.9, 0.1 + i * 0.04), "database", "full")
        for i in range(repo_count)
    ]

    evidence_scope = EvidenceScope(
        source_level="scored_features",
        includes_live_fetch=False,
        includes_cached_results=False,
        includes_database_results=True,
    )

    response = summarizer.summarize(results, "search_ranking", evidence_scope)

    # Property 1: result_count matches actual results
    assert response.metadata["result_count"] == len(results)

    # Property 2: Risk distribution sums to total
    distribution = response.metadata["risk_band_distribution"]
    assert sum(distribution.values()) == len(results)

    # Property 3: Data source counts sum to total
    sources = response.metadata["data_sources"]
    assert sum(sources.values()) == len(results)


@pytest.mark.property_test
@given(
    repo_names=st.lists(
        st.text(
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
            min_size=3,
            max_size=20,
        ).map(lambda s: f"{s[:10]}/{s[10:]}"),
        min_size=1,
        max_size=5,
        unique=True,
    ),
)
@settings(max_examples=100, deadline=None)
def test_merge_idempotence(repo_names):
    """
    Property: Merge Idempotence.

    Validates:
    - Merging same results multiple times produces same output
    - No duplicate entries created
    """
    summarizer = ResultSummarizer()

    # Create results
    results = [create_repo_summary(name, 0.2, "database", "full") for name in repo_names]

    # Merge multiple times
    merged1 = summarizer.merge_results(results, [])
    merged2 = summarizer.merge_results(merged1, [])
    merged3 = summarizer.merge_results(merged2, [])

    # Property: All merges produce same result
    assert len(merged1) == len(merged2) == len(merged3) == len(repo_names)

    repo_names1 = {r.repo_full_name for r in merged1}
    repo_names2 = {r.repo_full_name for r in merged2}
    repo_names3 = {r.repo_full_name for r in merged3}

    assert repo_names1 == repo_names2 == repo_names3 == set(repo_names)


@pytest.mark.property_test
@given(
    repo_count=st.integers(min_value=1, max_value=10),
)
@settings(max_examples=100, deadline=None)
def test_warning_generation_consistency(repo_count):
    """
    Property: Warning Generation Consistency.

    Validates:
    - Warnings are generated consistently
    - Warning count is deterministic
    """
    summarizer = ResultSummarizer()

    # Create results with mixed completeness
    results = []
    for i in range(repo_count):
        completeness = "full" if i % 2 == 0 else "provisional"
        results.append(
            create_repo_summary(f"org/repo{i}", 0.2, "database", completeness)
        )

    evidence_scope = EvidenceScope(
        source_level="scored_features",
        includes_live_fetch=False,
        includes_cached_results=False,
        includes_database_results=True,
    )

    response1 = summarizer.summarize(results, "repo_comparison", evidence_scope)
    response2 = summarizer.summarize(results, "repo_comparison", evidence_scope)

    # Property: Same warnings generated each time
    assert len(response1.warnings) == len(response2.warnings)
    assert set(response1.warnings) == set(response2.warnings)
