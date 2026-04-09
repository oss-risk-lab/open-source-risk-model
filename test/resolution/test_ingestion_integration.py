"""Tests for ingestion pipeline integration with transitive resolution (Req 13)."""
import tempfile
import os
import logging
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime, timezone

import pytest

from open_source_risk_model.dependencies.ingestion_service import (
    DependencyIngestionService,
    IngestionResult,
)
from open_source_risk_model.persistence.db import get_connection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service(db_path):
    """Create a DependencyIngestionService with mocked DB init and repos."""
    with patch("open_source_risk_model.dependencies.ingestion_service.DependencyRepository") as mock_dep_repo:
        with patch("open_source_risk_model.dependencies.ingestion_service.PackageMappingRepository"):
            mock_dep_repo_inst = MagicMock()
            mock_dep_repo_inst.get_dependencies.return_value = []
            mock_dep_repo.return_value = mock_dep_repo_inst
            service = DependencyIngestionService(db_path=db_path)
            return service


def _run_successful_ingestion(service, repo, resolve_transitive, dep_count=1):
    """Run ingest_repo with mocks that produce a successful result with dep_count deps."""
    mock_dep = MagicMock()
    mock_dep.manifest_path = "requirements.txt"
    deps = [mock_dep] * dep_count

    with patch("open_source_risk_model.dependencies.ingestion_service.ManifestDiscovery") as mock_disc:
        mock_disc_inst = MagicMock()
        mock_disc_inst.discover_manifests.return_value = ["requirements.txt"]
        mock_disc.return_value = mock_disc_inst

        with patch.object(service, '_fetch_file_content', return_value="requests>=2.0\n"):
            with patch.object(service.parser_registry, 'parse_file', return_value=deps):
                with patch.object(service, '_resolve_packages', return_value=0):
                    with patch.object(service, '_ensure_repo_graph_exists'):
                        result = service.ingest_repo(
                            repo, refresh=True, resolve_transitive=resolve_transitive
                        )
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestResolveTransitiveDefault:
    """resolve_transitive=False (default) does not trigger resolution."""

    def test_default_does_not_trigger_resolution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            service = _make_service(db_path)

            # Patch the resolution modules at their source so the lazy import picks them up
            with patch("open_source_risk_model.resolution.resolver.TransitiveResolver") as mock_resolver_cls:
                with patch("open_source_risk_model.resolution.storage.ResolvedDependencyStorage") as mock_storage_cls:
                    result = _run_successful_ingestion(service, "owner/repo", resolve_transitive=False)

                    assert result.success
                    assert result.dependencies_found == 1
                    # TransitiveResolver should NOT have been instantiated
                    mock_resolver_cls.assert_not_called()
                    mock_storage_cls.assert_not_called()


class TestResolveTransitiveTriggered:
    """resolve_transitive=True with successful ingestion triggers resolution."""

    def test_triggers_resolution_on_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            service = _make_service(db_path)

            mock_resolver = MagicMock()
            mock_resolver.resolve_repo.return_value = ([], MagicMock(total_edges=0, error_count=0))
            mock_storage = MagicMock()

            with patch("open_source_risk_model.resolution.resolver.TransitiveResolver", return_value=mock_resolver) as mock_resolver_cls:
                with patch("open_source_risk_model.resolution.storage.ResolvedDependencyStorage", return_value=mock_storage) as mock_storage_cls:
                    result = _run_successful_ingestion(service, "owner/repo", resolve_transitive=True)

                    assert result.success
                    mock_resolver_cls.assert_called_once_with(db_path=db_path)
                    mock_resolver.resolve_repo.assert_called_once_with("owner/repo")
                    mock_storage_cls.assert_called_once_with(db_path)
                    mock_storage.store_edges.assert_called_once()


class TestResolveTransitiveFailedIngestion:
    """resolve_transitive=True with failed ingestion does not trigger resolution."""

    def test_failed_ingestion_skips_resolution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            service = _make_service(db_path)

            with patch("open_source_risk_model.dependencies.ingestion_service.ManifestDiscovery") as mock_disc:
                mock_disc_inst = MagicMock()
                mock_disc_inst.discover_manifests.return_value = ["requirements.txt"]
                mock_disc.return_value = mock_disc_inst

                # Force an exception to produce a failed result
                with patch.object(service, '_ensure_repo_graph_exists', side_effect=Exception("DB error")):
                    service.dep_repo.get_dependencies.return_value = []

                    with patch("open_source_risk_model.resolution.resolver.TransitiveResolver") as mock_resolver_cls:
                        result = service.ingest_repo(
                            "owner/repo", refresh=True, resolve_transitive=True
                        )
                        assert not result.success
                        mock_resolver_cls.assert_not_called()


class TestResolveTransitiveZeroDeps:
    """resolve_transitive=True with zero dependencies does not trigger resolution."""

    def test_zero_deps_skips_resolution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            service = _make_service(db_path)

            with patch("open_source_risk_model.dependencies.ingestion_service.ManifestDiscovery") as mock_disc:
                mock_disc_inst = MagicMock()
                # No manifests → dependencies_found=0
                mock_disc_inst.discover_manifests.return_value = []
                mock_disc.return_value = mock_disc_inst

                with patch("open_source_risk_model.resolution.resolver.TransitiveResolver") as mock_resolver_cls:
                    result = service.ingest_repo(
                        "owner/repo", refresh=True, resolve_transitive=True
                    )
                    assert result.success
                    assert result.dependencies_found == 0
                    mock_resolver_cls.assert_not_called()


class TestResolutionFailureCaught:
    """Resolution failure is caught and logged, ingestion result still returned (Req 13.3)."""

    def test_resolution_failure_does_not_abort_ingestion(self, caplog):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            service = _make_service(db_path)

            with patch(
                "open_source_risk_model.resolution.resolver.TransitiveResolver",
                side_effect=RuntimeError("Resolution exploded"),
            ):
                with caplog.at_level(logging.ERROR):
                    result = _run_successful_ingestion(
                        service, "owner/repo", resolve_transitive=True
                    )
                    # Ingestion result is still returned successfully
                    assert result.success
                    assert result.dependencies_found == 1
                    # Error was logged
                    assert any(
                        "Transitive resolution failed" in record.message
                        for record in caplog.records
                    )


class TestRepoDependenciesNotModified:
    """repo_dependencies table is not modified by resolution (Req 13.4)."""

    def test_repo_dependencies_unchanged_after_resolution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")

            # Create service first (initializes full DB schema)
            service = _make_service(db_path)

            # Seed repo_dependencies with data matching the real schema
            conn = get_connection(db_path)
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO repo_dependencies "
                "(repo_full_name, package_name, registry_type, manifest_path, confidence, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("owner/repo", "requests", "pypi", "requirements.txt", 1.0, now),
            )
            conn.execute(
                "INSERT INTO repo_dependencies "
                "(repo_full_name, package_name, registry_type, manifest_path, confidence, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("owner/repo", "flask", "pypi", "requirements.txt", 1.0, now),
            )
            conn.commit()
            initial_count = conn.execute(
                "SELECT COUNT(*) FROM repo_dependencies WHERE repo_full_name = ?",
                ("owner/repo",),
            ).fetchone()[0]
            conn.close()
            assert initial_count == 2

            mock_resolver = MagicMock()
            mock_resolver.resolve_repo.return_value = (
                [MagicMock()],  # some edges
                MagicMock(total_edges=1, error_count=0),
            )
            mock_storage = MagicMock()

            with patch("open_source_risk_model.resolution.resolver.TransitiveResolver", return_value=mock_resolver):
                with patch("open_source_risk_model.resolution.storage.ResolvedDependencyStorage", return_value=mock_storage):
                    result = _run_successful_ingestion(
                        service, "owner/repo", resolve_transitive=True
                    )
                    assert result.success

            # Verify repo_dependencies was not modified
            conn = get_connection(db_path)
            final_count = conn.execute(
                "SELECT COUNT(*) FROM repo_dependencies WHERE repo_full_name = ?",
                ("owner/repo",),
            ).fetchone()[0]
            conn.close()
            assert final_count == initial_count
