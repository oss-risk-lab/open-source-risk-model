"""
Property-based tests for RiskMetadataEnricher.

Feature: dependency-tree-view
Property 5: Risk Classification Accuracy
Property 4: Risk Metadata Completeness
Property 6: Missing Data Provenance

Validates: Requirements 2.1–2.6
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile

import pytest
from hypothesis import given, settings, strategies as st

from open_source_risk_model.tree.enricher import RiskMetadataEnricher
from open_source_risk_model.tree.models import TreeNode


# ======================================================================
# Helpers
# ======================================================================


def _create_test_db(
    *,
    package_mappings: list[tuple] | None = None,
    repo_graphs: list[dict] | None = None,
    repo_cves: list[tuple] | None = None,
    repo_maintainers: list[tuple] | None = None,
) -> str:
    """Create a temporary SQLite database with test data."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE package_mappings (
            package_name TEXT NOT NULL,
            registry_type TEXT NOT NULL,
            repo_full_name TEXT,
            resolution_method TEXT NOT NULL DEFAULT 'test',
            confidence REAL NOT NULL DEFAULT 1.0,
            metadata TEXT,
            created_at TEXT NOT NULL DEFAULT '2024-01-01T00:00:00Z',
            updated_at TEXT NOT NULL DEFAULT '2024-01-01T00:00:00Z',
            PRIMARY KEY (package_name, registry_type)
        );

        CREATE TABLE repo_graphs (
            repo_full_name TEXT PRIMARY KEY,
            graph_json TEXT NOT NULL,
            schema_version TEXT NOT NULL DEFAULT '1.0',
            node_count INTEGER NOT NULL DEFAULT 0,
            edge_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT '2024-01-01T00:00:00Z',
            updated_at TEXT NOT NULL DEFAULT '2024-01-15T10:30:00Z',
            data_sources TEXT NOT NULL DEFAULT '[]',
            warnings TEXT,
            generation_time_ms INTEGER DEFAULT 0
        );

        CREATE TABLE repo_cves (
            repo_full_name TEXT NOT NULL,
            cve_id TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'UNKNOWN',
            cvss_score REAL,
            affected_releases TEXT,
            PRIMARY KEY (repo_full_name, cve_id)
        );

        CREATE TABLE repo_maintainers (
            repo_full_name TEXT NOT NULL,
            maintainer_username TEXT NOT NULL,
            contribution_fraction REAL NOT NULL DEFAULT 0.0,
            commit_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (repo_full_name, maintainer_username)
        );
    """)

    if package_mappings:
        conn.executemany(
            "INSERT INTO package_mappings (package_name, registry_type, repo_full_name) VALUES (?, ?, ?)",
            package_mappings,
        )

    if repo_graphs:
        for rg in repo_graphs:
            conn.execute(
                "INSERT INTO repo_graphs (repo_full_name, graph_json, node_count, edge_count) VALUES (?, ?, ?, ?)",
                (rg["repo"], rg["graph_json"], rg.get("node_count", 1), rg.get("edge_count", 0)),
            )

    if repo_cves:
        conn.executemany(
            "INSERT INTO repo_cves (repo_full_name, cve_id, severity) VALUES (?, ?, ?)",
            repo_cves,
        )

    if repo_maintainers:
        conn.executemany(
            "INSERT INTO repo_maintainers (repo_full_name, maintainer_username, contribution_fraction, commit_count) VALUES (?, ?, ?, ?)",
            repo_maintainers,
        )

    conn.commit()
    conn.close()
    return db_path


def _make_graph_json(
    repo: str,
    maintenance_risk: float | None = None,
    days_since_release: int | None = None,
) -> str:
    """Build a minimal graph JSON with a repo node and optional release node."""
    nodes = []
    repo_meta: dict = {}
    if maintenance_risk is not None:
        repo_meta["maintenance_risk"] = maintenance_risk
    nodes.append({"id": f"repo:{repo}", "type": "repo", "label": repo, "metadata": repo_meta})

    if days_since_release is not None:
        nodes.append({
            "id": f"release:{repo}:latest",
            "type": "release",
            "label": "latest",
            "metadata": {"days_since_release": days_since_release},
        })

    return json.dumps({"nodes": nodes, "edges": []})


# ======================================================================
# Strategies
# ======================================================================

# Scores in the valid 0–100 range (ints and floats) plus None
valid_scores = st.one_of(
    st.none(),
    st.integers(min_value=0, max_value=100),
    st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False),
)

ecosystems = st.sampled_from(["npm", "pypi", "maven", "go"])

package_names = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789-_",
    min_size=1,
    max_size=30,
).filter(lambda s: s[0].isalpha())

versions = st.from_regex(r"[0-9]+\.[0-9]+\.[0-9]+", fullmatch=True)


# ======================================================================
# Property 5: Risk Classification Accuracy
# ======================================================================


class TestRiskClassificationAccuracy:
    """
    **Validates: Requirements 2.3**

    Property 5: Risk Classification Accuracy — risk_level matches
    risk_score thresholds for all scores 0–100 and None.

    For any score in [0, 100] or None, _classify_risk_level returns:
      - None when score is None
      - "low" when score <= 30
      - "medium" when 31 <= score <= 70
      - "high" when score > 70
    """

    @given(score=st.none())
    @settings(max_examples=10)
    def test_none_score_returns_none(self, score):
        """**Validates: Requirements 2.3** — None score → None level."""
        result = RiskMetadataEnricher._classify_risk_level(score)
        assert result is None

    @given(score=st.integers(min_value=0, max_value=30))
    @settings(max_examples=100)
    def test_low_risk_integer_scores(self, score):
        """**Validates: Requirements 2.3** — integer scores 0–30 → 'low'."""
        result = RiskMetadataEnricher._classify_risk_level(score)
        assert result == "low"

    @given(score=st.floats(min_value=0.0, max_value=30.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_low_risk_float_scores(self, score):
        """**Validates: Requirements 2.3** — float scores 0.0–30.0 → 'low'."""
        result = RiskMetadataEnricher._classify_risk_level(score)
        assert result == "low"

    @given(score=st.integers(min_value=31, max_value=70))
    @settings(max_examples=100)
    def test_medium_risk_integer_scores(self, score):
        """**Validates: Requirements 2.3** — integer scores 31–70 → 'medium'."""
        result = RiskMetadataEnricher._classify_risk_level(score)
        assert result == "medium"

    @given(score=st.floats(min_value=30.01, max_value=70.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_medium_risk_float_scores(self, score):
        """**Validates: Requirements 2.3** — float scores (30, 70] → 'medium'."""
        result = RiskMetadataEnricher._classify_risk_level(score)
        assert result == "medium"

    @given(score=st.integers(min_value=71, max_value=100))
    @settings(max_examples=100)
    def test_high_risk_integer_scores(self, score):
        """**Validates: Requirements 2.3** — integer scores 71–100 → 'high'."""
        result = RiskMetadataEnricher._classify_risk_level(score)
        assert result == "high"

    @given(score=st.floats(min_value=70.01, max_value=100.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=100)
    def test_high_risk_float_scores(self, score):
        """**Validates: Requirements 2.3** — float scores (70, 100] → 'high'."""
        result = RiskMetadataEnricher._classify_risk_level(score)
        assert result == "high"

    @given(score=valid_scores)
    @settings(max_examples=200)
    def test_classification_covers_all_valid_scores(self, score):
        """**Validates: Requirements 2.3** — all valid scores produce a valid classification."""
        result = RiskMetadataEnricher._classify_risk_level(score)
        if score is None:
            assert result is None
        else:
            assert result in ("low", "medium", "high")
            if score <= 30:
                assert result == "low"
            elif score <= 70:
                assert result == "medium"
            else:
                assert result == "high"


# ======================================================================
# Property 4: Risk Metadata Completeness
# ======================================================================


class TestRiskMetadataCompleteness:
    """
    **Validates: Requirements 2.1, 2.2, 2.4, 2.5**

    Property 4: Risk Metadata Completeness — when score_source="repo_graph",
    risk_score and vulnerability_count are populated.
    """

    @given(
        maintenance_risk=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
        vuln_count=st.integers(min_value=0, max_value=20),
        pkg_name=package_names,
        eco=ecosystems,
        ver=versions,
    )
    @settings(max_examples=100)
    def test_repo_graph_source_has_score_and_vulns(
        self, maintenance_risk, vuln_count, pkg_name, eco, ver
    ):
        """**Validates: Requirements 2.1, 2.2**

        When a node has score_source="repo_graph", risk_score must not be
        None and vulnerability_count must be an int >= 0.
        """
        repo_name = f"owner/{pkg_name}-repo"

        cves = [
            (repo_name, f"CVE-2024-{i:04d}", "HIGH")
            for i in range(vuln_count)
        ]

        db_path = _create_test_db(
            package_mappings=[(pkg_name, eco, repo_name)],
            repo_graphs=[{
                "repo": repo_name,
                "graph_json": _make_graph_json(repo_name, maintenance_risk=maintenance_risk),
            }],
            repo_cves=cves if cves else None,
        )

        try:
            node = TreeNode(
                id=f"pkg:{eco}/{pkg_name}@{ver}",
                node_type="package",
                name=pkg_name,
                version=ver,
                ecosystem=eco,
            )
            RiskMetadataEnricher.enrich_nodes([node], db_path)

            rm = node.risk_metadata
            assert rm is not None
            assert rm.score_source == "repo_graph"
            assert rm.risk_score is not None
            assert isinstance(rm.risk_score, (int, float))
            assert 0 <= rm.risk_score <= 100
            assert isinstance(rm.vulnerability_count, int)
            assert rm.vulnerability_count >= 0
            assert rm.vulnerability_count == vuln_count

            # risk_level must be consistent with risk_score
            expected_level = RiskMetadataEnricher._classify_risk_level(rm.risk_score)
            assert rm.risk_level == expected_level

            # score_completeness must be "full" or "partial" (not "missing")
            assert rm.score_completeness in ("full", "partial")
        finally:
            os.unlink(db_path)


# ======================================================================
# Property 6: Missing Data Provenance
# ======================================================================


class TestMissingDataProvenance:
    """
    **Validates: Requirements 2.6**

    Property 6: Missing Data Provenance — nodes without risk data have
    score_source="unavailable" and score_completeness="missing".
    """

    @given(
        pkg_name=package_names,
        eco=ecosystems,
        ver=versions,
    )
    @settings(max_examples=100)
    def test_no_mapping_yields_unavailable(self, pkg_name, eco, ver):
        """**Validates: Requirements 2.6**

        When no package_mapping exists, score_source must be "unavailable"
        and score_completeness must be "missing".
        """
        db_path = _create_test_db()

        try:
            node = TreeNode(
                id=f"pkg:{eco}/{pkg_name}@{ver}",
                node_type="package",
                name=pkg_name,
                version=ver,
                ecosystem=eco,
            )
            RiskMetadataEnricher.enrich_nodes([node], db_path)

            rm = node.risk_metadata
            assert rm is not None
            assert rm.score_source == "unavailable"
            assert rm.score_completeness == "missing"
            assert rm.risk_score is None
            assert rm.risk_level is None
        finally:
            os.unlink(db_path)

    @given(
        pkg_name=package_names,
        eco=ecosystems,
        ver=versions,
    )
    @settings(max_examples=100)
    def test_mapping_without_repo_graph_yields_unavailable(self, pkg_name, eco, ver):
        """**Validates: Requirements 2.6**

        When package_mapping exists but repo_graphs has no entry,
        score_source must be "unavailable" and score_completeness must be "missing".
        """
        repo_name = f"owner/{pkg_name}-repo"
        db_path = _create_test_db(
            package_mappings=[(pkg_name, eco, repo_name)],
        )

        try:
            node = TreeNode(
                id=f"pkg:{eco}/{pkg_name}@{ver}",
                node_type="package",
                name=pkg_name,
                version=ver,
                ecosystem=eco,
            )
            RiskMetadataEnricher.enrich_nodes([node], db_path)

            rm = node.risk_metadata
            assert rm is not None
            assert rm.score_source == "unavailable"
            assert rm.score_completeness == "missing"
            assert rm.risk_score is None
            assert rm.risk_level is None
        finally:
            os.unlink(db_path)
