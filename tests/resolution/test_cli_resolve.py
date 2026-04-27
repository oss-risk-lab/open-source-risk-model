"""Tests for CLI resolution command."""
import sys
from unittest.mock import patch, MagicMock

import pytest

from open_source_risk_model.resolution.models import ResolutionEdge, ResolutionSummary


MODULE = "open_source_risk_model.cli.resolve"


def _make_summary(repo="owner/repo", total=5, resolved=3, errors=1,
                  cycles=0, max_depth=0, budget=0, unsupported=1,
                  actual_max=2, api_calls=3, cache_hits=1, elapsed=1.5,
                  edges_per_depth=None):
    """Helper to build a ResolutionSummary for tests."""
    return ResolutionSummary(
        repo_full_name=repo,
        total_edges=total,
        resolved_count=resolved,
        error_count=errors,
        cycle_count=cycles,
        max_depth_reached_count=max_depth,
        unsupported_ecosystem_count=unsupported,
        budget_exhausted_count=budget,
        actual_max_depth=actual_max,
        api_calls_made=api_calls,
        cache_hits=cache_hits,
        elapsed_seconds=elapsed,
        edges_per_depth=edges_per_depth or {1: 3, 2: 2},
    )


def _make_edges(count=3):
    """Helper to build a list of ResolutionEdge objects."""
    return [
        ResolutionEdge(
            repo_full_name="owner/repo",
            parent_ecosystem=None,
            parent_package="owner/repo",
            child_ecosystem="pypi",
            child_package=f"pkg-{i}",
            declared_specifier=None,
            resolved_version="1.0.0",
            depth=1,
            resolution_status="resolved",
            source_registry="pypi",
            resolved_at="2024-01-01T00:00:00+00:00",
        )
        for i in range(count)
    ]


class TestCliResolveRepoRequired:
    """--repo is required."""

    def test_missing_repo_exits_with_error(self):
        with patch.object(sys, "argv", ["resolve"]):
            with pytest.raises(SystemExit) as exc_info:
                from open_source_risk_model.cli.resolve import main
                main()
            assert exc_info.value.code == 2  # argparse exits 2 for missing required


class TestCliResolveSuccess:
    """Successful resolution prints summary and exits 0."""

    @patch(f"{MODULE}.ResolvedDependencyStorage")
    @patch(f"{MODULE}.TransitiveResolver")
    def test_successful_resolution(self, MockResolver, MockStorage, capsys):
        mock_storage = MockStorage.return_value
        mock_storage.has_resolved_data.return_value = False

        mock_resolver = MockResolver.return_value
        edges = _make_edges(3)
        summary = _make_summary()
        mock_resolver._get_direct_deps.return_value = [
            {"package_name": "requests", "ecosystem": "pypi", "version_spec": ">=2.0"},
        ]
        mock_resolver.resolve_repo.return_value = (edges, summary)

        with patch.object(sys, "argv", ["resolve", "--repo", "owner/repo"]):
            from open_source_risk_model.cli.resolve import main
            result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert "Resolution complete for owner/repo" in captured.out
        assert "Total edges:" in captured.out
        assert "Resolved:" in captured.out
        mock_storage.store_edges.assert_called_once_with("owner/repo", edges)


class TestCliResolveNoDeps:
    """No direct deps prints error to stderr and exits 1."""

    @patch(f"{MODULE}.ResolvedDependencyStorage")
    @patch(f"{MODULE}.TransitiveResolver")
    def test_no_direct_deps_exits_1(self, MockResolver, MockStorage, capsys):
        mock_storage = MockStorage.return_value
        mock_storage.has_resolved_data.return_value = False

        mock_resolver = MockResolver.return_value
        mock_resolver._get_direct_deps.return_value = []

        with patch.object(sys, "argv", ["resolve", "--repo", "owner/repo"]):
            from open_source_risk_model.cli.resolve import main
            result = main()

        assert result == 1
        captured = capsys.readouterr()
        assert "No direct dependencies found" in captured.err
        assert "Run dependency ingestion first" in captured.err


class TestCliResolveForce:
    """--force re-resolves even when data exists."""

    @patch(f"{MODULE}.ResolvedDependencyStorage")
    @patch(f"{MODULE}.TransitiveResolver")
    def test_force_flag_skips_existing_check(self, MockResolver, MockStorage, capsys):
        mock_storage = MockStorage.return_value
        mock_storage.has_resolved_data.return_value = True

        mock_resolver = MockResolver.return_value
        edges = _make_edges(2)
        summary = _make_summary(total=2, resolved=2, errors=0, unsupported=0)
        mock_resolver._get_direct_deps.return_value = [
            {"package_name": "flask", "ecosystem": "pypi"},
        ]
        mock_resolver.resolve_repo.return_value = (edges, summary)

        with patch.object(sys, "argv", ["resolve", "--repo", "owner/repo", "--force"]):
            from open_source_risk_model.cli.resolve import main
            result = main()

        assert result == 0
        # Should have resolved despite existing data
        mock_resolver.resolve_repo.assert_called_once()
        mock_storage.store_edges.assert_called_once()


class TestCliResolveExistingData:
    """Without --force, existing data prints skip message and exits 0."""

    @patch(f"{MODULE}.ResolvedDependencyStorage")
    @patch(f"{MODULE}.TransitiveResolver")
    def test_existing_data_skips(self, MockResolver, MockStorage, capsys):
        mock_storage = MockStorage.return_value
        mock_storage.has_resolved_data.return_value = True
        mock_storage.get_oldest_resolved_at.return_value = "2024-01-01T00:00:00+00:00"

        with patch.object(sys, "argv", ["resolve", "--repo", "owner/repo"]):
            from open_source_risk_model.cli.resolve import main
            result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert "Resolved data already exists" in captured.out
        assert "Use --force to re-resolve" in captured.out
        # Resolver should NOT have been called
        MockResolver.return_value.resolve_repo.assert_not_called()


class TestCliResolveEcosystemFilter:
    """--ecosystems pypi filters to PyPI only."""

    @patch(f"{MODULE}.ResolvedDependencyStorage")
    @patch(f"{MODULE}.TransitiveResolver")
    def test_ecosystems_filter(self, MockResolver, MockStorage):
        mock_storage = MockStorage.return_value
        mock_storage.has_resolved_data.return_value = False

        mock_resolver = MockResolver.return_value
        mock_resolver._get_direct_deps.return_value = [
            {"package_name": "requests", "ecosystem": "pypi"},
        ]
        mock_resolver.resolve_repo.return_value = (_make_edges(1), _make_summary(total=1, resolved=1, errors=0, unsupported=0))

        with patch.object(sys, "argv", ["resolve", "--repo", "owner/repo", "--ecosystems", "pypi"]):
            from open_source_risk_model.cli.resolve import main
            main()

        # Verify TransitiveResolver was created with ecosystem_filter={"pypi"}
        call_kwargs = MockResolver.call_args[1]
        assert call_kwargs["ecosystem_filter"] == {"pypi"}


class TestCliResolveBudgetOverride:
    """--budget 50 overrides default budget."""

    @patch(f"{MODULE}.ResolvedDependencyStorage")
    @patch(f"{MODULE}.TransitiveResolver")
    @patch(f"{MODULE}.BudgetConfig")
    def test_budget_override(self, MockBudgetConfig, MockResolver, MockStorage):
        mock_storage = MockStorage.return_value
        mock_storage.has_resolved_data.return_value = False

        mock_resolver = MockResolver.return_value
        mock_resolver._get_direct_deps.return_value = [
            {"package_name": "requests", "ecosystem": "pypi"},
        ]
        mock_resolver.resolve_repo.return_value = (_make_edges(1), _make_summary(total=1, resolved=1, errors=0, unsupported=0))

        with patch.object(sys, "argv", ["resolve", "--repo", "owner/repo", "--budget", "50"]):
            from open_source_risk_model.cli.resolve import main
            main()

        MockBudgetConfig.assert_called_with(global_budget=50)


class TestCliResolveMaxDepthOverride:
    """--max-depth 3 overrides default depth."""

    @patch(f"{MODULE}.ResolvedDependencyStorage")
    @patch(f"{MODULE}.TransitiveResolver")
    def test_max_depth_override(self, MockResolver, MockStorage):
        mock_storage = MockStorage.return_value
        mock_storage.has_resolved_data.return_value = False

        mock_resolver = MockResolver.return_value
        mock_resolver._get_direct_deps.return_value = [
            {"package_name": "requests", "ecosystem": "pypi"},
        ]
        mock_resolver.resolve_repo.return_value = (_make_edges(1), _make_summary(total=1, resolved=1, errors=0, unsupported=0))

        with patch.object(sys, "argv", ["resolve", "--repo", "owner/repo", "--max-depth", "3"]):
            from open_source_risk_model.cli.resolve import main
            main()

        call_kwargs = MockResolver.call_args[1]
        assert call_kwargs["max_depth"] == 3


class TestCliResolvePartialFailures:
    """Partial failures (some errors) still exit 0."""

    @patch(f"{MODULE}.ResolvedDependencyStorage")
    @patch(f"{MODULE}.TransitiveResolver")
    def test_partial_failures_exit_0(self, MockResolver, MockStorage, capsys):
        mock_storage = MockStorage.return_value
        mock_storage.has_resolved_data.return_value = False

        mock_resolver = MockResolver.return_value
        mock_resolver._get_direct_deps.return_value = [
            {"package_name": "requests", "ecosystem": "pypi"},
            {"package_name": "broken-pkg", "ecosystem": "pypi"},
        ]
        summary = _make_summary(total=5, resolved=3, errors=2)
        mock_resolver.resolve_repo.return_value = (_make_edges(5), summary)

        with patch.object(sys, "argv", ["resolve", "--repo", "owner/repo"]):
            from open_source_risk_model.cli.resolve import main
            result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert "Errors:" in captured.out
