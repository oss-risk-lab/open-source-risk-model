"""Unit tests for the retry_rate_limited script.

Tests mock all external dependencies and verify:
- main() returns 0 when all repos succeed
- main() returns 1 when a rate-limit (403) error occurs
- main() returns 1 when ingestion succeeds but validation fails

Requirements: 1.1, 1.6
"""
from __future__ import annotations

import importlib
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helper: load the script as a module (it lives outside the package tree)
# ---------------------------------------------------------------------------
def _load_retry_module() -> ModuleType:
    """Import scripts/retry_rate_limited.py as a module."""
    project_root = Path(__file__).resolve().parent.parent.parent
    script_path = project_root / "scripts" / "retry_rate_limited.py"
    spec = importlib.util.spec_from_file_location("retry_rate_limited", script_path)
    mod = importlib.util.module_from_spec(spec)
    # Ensure project root is on sys.path so the script's own sys.path hack works
    root_str = str(project_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    spec.loader.exec_module(mod)
    return mod


retry_mod = _load_retry_module()
run_pipeline = retry_mod.run_pipeline
validate_result = retry_mod.validate_result
main = retry_mod.main


# ---------------------------------------------------------------------------
# Helpers for building mock return values
# ---------------------------------------------------------------------------
@dataclass
class _FakeIngestionResult:
    success: bool
    dependencies_found: int = 10
    dependencies_resolved: int = 5
    errors: list[str] = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


@dataclass
class _FakeResolutionSummary:
    resolved_count: int = 8
    error_count: int = 0
    total_edges: int = 12


@dataclass
class _FakeInsight:
    graph_signal_score: float = 0.45
    graph_signal_label: str = "MEDIUM"


def _success_result(repo: str) -> dict:
    """A result dict representing a fully successful pipeline run."""
    return {
        "repo": repo,
        "success": True,
        "dep_count": 5,
        "edge_count": 10,
        "insight_score": 0.45,
        "error": None,
    }


def _failed_result(repo: str, error: str) -> dict:
    """A result dict representing a failed pipeline run."""
    return {
        "repo": repo,
        "success": False,
        "dep_count": 0,
        "edge_count": 0,
        "insight_score": None,
        "error": error,
    }


# ---------------------------------------------------------------------------
# validate_result tests
# ---------------------------------------------------------------------------
class TestValidateResult:
    """Tests for the validate_result function."""

    def test_valid_result_returns_no_failures(self):
        result = _success_result("owner/repo")
        failures = validate_result(result)
        assert failures == []

    def test_pipeline_not_complete_returns_failure(self):
        result = _failed_result("owner/repo", "Ingestion exception: 403")
        failures = validate_result(result)
        assert len(failures) == 1
        assert "Pipeline did not complete" in failures[0]

    def test_zero_dep_count_returns_failure(self):
        result = _success_result("owner/repo")
        result["dep_count"] = 0
        failures = validate_result(result)
        assert any("Dependency count is 0" in f for f in failures)

    def test_zero_edge_count_returns_failure(self):
        result = _success_result("owner/repo")
        result["edge_count"] = 0
        failures = validate_result(result)
        assert any("Graph edge count is 0" in f for f in failures)

    def test_null_insight_score_returns_failure(self):
        result = _success_result("owner/repo")
        result["insight_score"] = None
        failures = validate_result(result)
        assert any("Insight score is null" in f for f in failures)

    def test_multiple_validation_failures(self):
        result = _success_result("owner/repo")
        result["dep_count"] = 0
        result["edge_count"] = 0
        result["insight_score"] = None
        failures = validate_result(result)
        assert len(failures) == 3


# ---------------------------------------------------------------------------
# Patch targets — all in the loaded script module
# ---------------------------------------------------------------------------
_MOD = "retry_rate_limited"


# ---------------------------------------------------------------------------
# main() — all repos succeed → exit 0
# ---------------------------------------------------------------------------
class TestMainSuccess:
    """main() returns 0 when all repos pass pipeline + validation."""

    @patch.object(retry_mod, "run_pipeline")
    @patch.object(retry_mod, "validate_result", return_value=[])
    def test_returns_zero_on_full_success(self, mock_validate, mock_pipeline):
        mock_pipeline.side_effect = [
            _success_result("yaml/pyyaml"),
            _success_result("ytdl-org/youtube-dl"),
        ]
        assert main() == 0

    @patch.object(retry_mod, "run_pipeline")
    @patch.object(retry_mod, "validate_result", return_value=[])
    def test_calls_pipeline_for_each_target_repo(self, mock_validate, mock_pipeline):
        mock_pipeline.side_effect = [
            _success_result("yaml/pyyaml"),
            _success_result("ytdl-org/youtube-dl"),
        ]
        main()
        assert mock_pipeline.call_count == 2


# ---------------------------------------------------------------------------
# main() — rate-limit (403) failure → exit 1
# ---------------------------------------------------------------------------
class TestMainRateLimitFailure:
    """main() returns 1 when a rate-limit 403 error occurs."""

    @patch.object(retry_mod, "run_pipeline")
    def test_returns_one_on_rate_limit_error(self, mock_pipeline):
        mock_pipeline.side_effect = [
            _failed_result("yaml/pyyaml", "Ingestion exception: HTTP 403 rate limit"),
            _success_result("ytdl-org/youtube-dl"),
        ]
        assert main() == 1

    @patch.object(retry_mod, "run_pipeline")
    def test_continues_to_next_repo_after_failure(self, mock_pipeline):
        mock_pipeline.side_effect = [
            _failed_result("yaml/pyyaml", "Ingestion exception: HTTP 403 rate limit"),
            _success_result("ytdl-org/youtube-dl"),
        ]
        main()
        # Both repos should still be attempted
        assert mock_pipeline.call_count == 2

    @patch.object(retry_mod, "run_pipeline")
    def test_logs_rate_limit_failure(self, mock_pipeline, caplog):
        mock_pipeline.side_effect = [
            _failed_result("yaml/pyyaml", "Ingestion exception: HTTP 403 rate limit"),
            _success_result("ytdl-org/youtube-dl"),
        ]
        with caplog.at_level(logging.ERROR):
            main()
        assert any("FAILED" in r.message and "yaml/pyyaml" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# main() — partial failure (ingestion ok, validation fails) → exit 1
# ---------------------------------------------------------------------------
class TestMainPartialFailure:
    """main() returns 1 when ingestion succeeds but validation fails."""

    @patch.object(retry_mod, "run_pipeline")
    def test_returns_one_when_dep_count_zero(self, mock_pipeline):
        result = _success_result("yaml/pyyaml")
        result["dep_count"] = 0  # validation will fail
        mock_pipeline.side_effect = [
            result,
            _success_result("ytdl-org/youtube-dl"),
        ]
        assert main() == 1

    @patch.object(retry_mod, "run_pipeline")
    def test_returns_one_when_insight_score_null(self, mock_pipeline):
        result = _success_result("yaml/pyyaml")
        result["insight_score"] = None  # validation will fail
        mock_pipeline.side_effect = [
            result,
            _success_result("ytdl-org/youtube-dl"),
        ]
        assert main() == 1

    @patch.object(retry_mod, "run_pipeline")
    def test_returns_one_when_edge_count_zero(self, mock_pipeline):
        result = _success_result("ytdl-org/youtube-dl")
        result["edge_count"] = 0  # validation will fail
        mock_pipeline.side_effect = [
            _success_result("yaml/pyyaml"),
            result,
        ]
        assert main() == 1


# ---------------------------------------------------------------------------
# run_pipeline() — full integration with mocked externals
# ---------------------------------------------------------------------------
class TestRunPipeline:
    """Tests for run_pipeline with all external deps mocked."""

    def _patch_all(self):
        """Return a dict of patches for all external dependencies."""
        patches = {
            "ingestion_service": patch.object(
                retry_mod, "DependencyIngestionService"
            ),
            "resolver": patch.object(retry_mod, "TransitiveResolver"),
            "storage": patch.object(retry_mod, "ResolvedDependencyStorage"),
            "enrich": patch.object(retry_mod, "enrich_repo_graph"),
            "compute": patch.object(retry_mod, "compute_repo_insight"),
            "dep_count": patch.object(retry_mod, "get_dependency_count"),
            "edge_count": patch.object(retry_mod, "get_graph_edge_count"),
            "GraphRepository": patch.object(retry_mod, "GraphRepository"),
        }
        return patches

    def test_successful_pipeline_returns_success(self):
        with (
            patch.object(retry_mod, "DependencyIngestionService") as mock_svc_cls,
            patch.object(retry_mod, "TransitiveResolver") as mock_resolver_cls,
            patch.object(retry_mod, "ResolvedDependencyStorage") as mock_storage_cls,
            patch.object(retry_mod, "enrich_repo_graph", return_value=(5, 10)) as mock_enrich,
            patch.object(retry_mod, "compute_repo_insight") as mock_compute,
            patch.object(retry_mod, "get_dependency_count", return_value=5) as mock_dep,
            patch.object(retry_mod, "get_graph_edge_count", return_value=10) as mock_edge,
            patch.object(retry_mod, "GraphRepository") as mock_graph_repo_cls,
        ):
            # Setup ingestion mock
            mock_svc = mock_svc_cls.return_value
            mock_svc.ingest_repo.return_value = _FakeIngestionResult(success=True)

            # Setup resolver mock
            mock_resolver = mock_resolver_cls.return_value
            mock_resolver.resolve_repo.return_value = (
                [],
                _FakeResolutionSummary(),
            )

            # Setup storage mock
            mock_storage = mock_storage_cls.return_value

            # Setup insight mock
            mock_compute.return_value = _FakeInsight()

            result = run_pipeline("yaml/pyyaml", "/tmp/test.db")

            assert result["success"] is True
            assert result["dep_count"] == 5
            assert result["edge_count"] == 10
            assert result["insight_score"] == 0.45

    def test_ingestion_failure_returns_error(self):
        with (
            patch.object(retry_mod, "DependencyIngestionService") as mock_svc_cls,
        ):
            mock_svc = mock_svc_cls.return_value
            mock_svc.ingest_repo.return_value = _FakeIngestionResult(
                success=False, errors=["HTTP 403 Forbidden"]
            )

            result = run_pipeline("yaml/pyyaml", "/tmp/test.db")

            assert result["success"] is False
            assert "403" in result["error"]

    def test_ingestion_exception_with_403_returns_error(self):
        with (
            patch.object(retry_mod, "DependencyIngestionService") as mock_svc_cls,
        ):
            mock_svc = mock_svc_cls.return_value
            mock_svc.ingest_repo.side_effect = Exception("HTTP 403 rate limit exceeded")

            result = run_pipeline("yaml/pyyaml", "/tmp/test.db")

            assert result["success"] is False
            assert "403" in result["error"]

    def test_resolution_failure_returns_error(self):
        with (
            patch.object(retry_mod, "DependencyIngestionService") as mock_svc_cls,
            patch.object(retry_mod, "TransitiveResolver") as mock_resolver_cls,
        ):
            mock_svc = mock_svc_cls.return_value
            mock_svc.ingest_repo.return_value = _FakeIngestionResult(success=True)

            mock_resolver = mock_resolver_cls.return_value
            mock_resolver.resolve_repo.side_effect = Exception("Resolution timeout")

            result = run_pipeline("yaml/pyyaml", "/tmp/test.db")

            assert result["success"] is False
            assert "Resolution failed" in result["error"]

    def test_enrichment_failure_returns_error(self):
        with (
            patch.object(retry_mod, "DependencyIngestionService") as mock_svc_cls,
            patch.object(retry_mod, "TransitiveResolver") as mock_resolver_cls,
            patch.object(retry_mod, "ResolvedDependencyStorage") as mock_storage_cls,
            patch.object(retry_mod, "enrich_repo_graph") as mock_enrich,
        ):
            mock_svc = mock_svc_cls.return_value
            mock_svc.ingest_repo.return_value = _FakeIngestionResult(success=True)

            mock_resolver = mock_resolver_cls.return_value
            mock_resolver.resolve_repo.return_value = ([], _FakeResolutionSummary())

            mock_enrich.side_effect = Exception("Graph build failed")

            result = run_pipeline("yaml/pyyaml", "/tmp/test.db")

            assert result["success"] is False
            assert "Enrichment failed" in result["error"]
