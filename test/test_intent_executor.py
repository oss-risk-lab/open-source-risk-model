"""
Tests for IntentExecutor

Tests cover:
- Happy path for each intent (11 intents)
- Parameter validation
- Determinism (same input = same output)
- SQL injection protection
- Invalid intent rejection
- Result structure validation
"""

import pytest
from open_source_risk_model.query.intent_executor import IntentExecutor, QueryResult


@pytest.fixture
def executor():
    """Create executor with test database."""
    return IntentExecutor(db_path="data/graphs.db")


class TestIntentExecution:
    """Test each intent's happy path."""
    
    def test_list_dependencies(self, executor):
        """Test listing direct dependencies of a repository."""
        result = executor.execute(
            intent="list_dependencies",
            parameters={"repo_full_name": "django/django"},
            max_results=10
        )
        
        assert result.intent == "list_dependencies"
        assert result.result_count > 0
        assert len(result.results) <= 10
        assert all("package_name" in r for r in result.results)
        assert all("registry_type" in r for r in result.results)
        assert result.execution_time_ms > 0
        assert result.metadata["repo_full_name"] == "django/django"
        assert result.metadata["direct_only"] is True
    
    def test_find_dependents(self, executor):
        """Test finding repositories that depend on a package."""
        result = executor.execute(
            intent="find_dependents",
            parameters={"package_name": "flask", "registry_type": "pypi"},
            max_results=10
        )
        
        assert result.intent == "find_dependents"
        assert result.result_count >= 0
        assert all("repo_full_name" in r for r in result.results)
        assert result.metadata["package_name"] == "flask"
        assert result.metadata["registry_type"] == "pypi"
    
    def test_get_dependency_tree(self, executor):
        """Test computing dependency tree with BFS."""
        result = executor.execute(
            intent="get_dependency_tree",
            parameters={"repo_full_name": "pallets/flask", "max_depth": 2},
            max_results=50
        )
        
        assert result.intent == "get_dependency_tree"
        assert result.result_count >= 0
        assert all("depth" in r for r in result.results)
        assert all("parent" in r for r in result.results)
        assert all(r["depth"] <= 2 for r in result.results)
        assert result.metadata["root_repo"] == "pallets/flask"
        assert result.metadata["max_depth"] == 2
    
    def test_check_resolution(self, executor):
        """Test checking if a package resolves to a GitHub repo."""
        result = executor.execute(
            intent="check_resolution",
            parameters={"package_name": "flask", "registry_type": "pypi"},
            max_results=1
        )
        
        assert result.intent == "check_resolution"
        assert result.result_count in [0, 1]
        if result.result_count == 1:
            assert "repo_full_name" in result.results[0]
            assert "confidence" in result.results[0]
        assert result.metadata["resolved"] == (result.result_count == 1)
    
    def test_list_unresolved(self, executor):
        """Test listing unresolved dependencies."""
        result = executor.execute(
            intent="list_unresolved",
            parameters={},
            max_results=10
        )
        
        assert result.intent == "list_unresolved"
        assert result.result_count >= 0
        assert all("package_name" in r for r in result.results)
        assert result.metadata["unresolved_count"] == result.result_count
    
    def test_list_manifests(self, executor):
        """Test listing manifest files for a repository."""
        result = executor.execute(
            intent="list_manifests",
            parameters={"repo_full_name": "django/django"},
            max_results=10
        )
        
        assert result.intent == "list_manifests"
        assert result.result_count >= 0
        assert all("manifest_path" in r for r in result.results)
        assert all("dependency_count" in r for r in result.results)
        assert result.metadata["repo_full_name"] == "django/django"
    
    def test_count_by_manifest_type(self, executor):
        """Test counting manifests by type."""
        result = executor.execute(
            intent="count_by_manifest_type",
            parameters={},
            max_results=100
        )
        
        assert result.intent == "count_by_manifest_type"
        assert result.result_count > 0
        assert all("manifest_type" in r for r in result.results)
        assert all("count" in r for r in result.results)
        assert all(r["count"] > 0 for r in result.results)
    
    def test_repo_stats(self, executor):
        """Test getting repository statistics."""
        result = executor.execute(
            intent="repo_stats",
            parameters={"repo_full_name": "django/django"},
            max_results=1
        )
        
        assert result.intent == "repo_stats"
        assert result.result_count == 1
        assert "total_dependencies" in result.results[0]
        assert "manifest_count" in result.results[0]
        assert "direct_dependencies" in result.results[0]
        assert "resolved_dependencies" in result.results[0]
    
    def test_dataset_stats(self, executor):
        """Test getting overall dataset statistics."""
        result = executor.execute(
            intent="dataset_stats",
            parameters={},
            max_results=1
        )
        
        assert result.intent == "dataset_stats"
        assert result.result_count == 1
        assert "repo_count" in result.results[0]
        assert "total_dependencies" in result.results[0]
        assert "resolution_rate" in result.results[0]
        assert result.results[0]["repo_count"] > 0
    
    def test_search_repos(self, executor):
        """Test searching repositories by name pattern."""
        result = executor.execute(
            intent="search_repos",
            parameters={"pattern": "django"},
            max_results=10
        )
        
        assert result.intent == "search_repos"
        assert result.result_count >= 0
        assert all("repo_full_name" in r for r in result.results)
        assert all("django" in r["repo_full_name"].lower() for r in result.results)
    
    def test_search_packages(self, executor):
        """Test searching packages by name pattern."""
        result = executor.execute(
            intent="search_packages",
            parameters={"pattern": "flask"},
            max_results=10
        )
        
        assert result.intent == "search_packages"
        assert result.result_count >= 0
        assert all("package_name" in r for r in result.results)
        assert all("used_by_count" in r for r in result.results)


class TestParameterValidation:
    """Test parameter validation for each intent."""
    
    def test_list_dependencies_missing_repo(self, executor):
        """Test that list_dependencies requires repo_full_name."""
        with pytest.raises(ValueError, match="repo_full_name is required"):
            executor.execute(
                intent="list_dependencies",
                parameters={},
                max_results=10
            )
    
    def test_find_dependents_missing_package(self, executor):
        """Test that find_dependents requires package_name."""
        with pytest.raises(ValueError, match="package_name is required"):
            executor.execute(
                intent="find_dependents",
                parameters={},
                max_results=10
            )
    
    def test_check_resolution_missing_params(self, executor):
        """Test that check_resolution requires both parameters."""
        with pytest.raises(ValueError, match="package_name and registry_type are required"):
            executor.execute(
                intent="check_resolution",
                parameters={"package_name": "flask"},
                max_results=1
            )
    
    def test_list_manifests_missing_repo(self, executor):
        """Test that list_manifests requires repo_full_name."""
        with pytest.raises(ValueError, match="repo_full_name is required"):
            executor.execute(
                intent="list_manifests",
                parameters={},
                max_results=10
            )
    
    def test_search_repos_missing_pattern(self, executor):
        """Test that search_repos requires pattern."""
        with pytest.raises(ValueError, match="pattern is required"):
            executor.execute(
                intent="search_repos",
                parameters={},
                max_results=10
            )


class TestDeterminism:
    """Test that queries are deterministic."""
    
    def test_same_query_same_results(self, executor):
        """Test that identical queries produce identical results."""
        params = {"repo_full_name": "django/django"}
        
        result1 = executor.execute("list_dependencies", params, max_results=10)
        result2 = executor.execute("list_dependencies", params, max_results=10)
        
        assert result1.result_count == result2.result_count
        assert result1.results == result2.results
        assert result1.metadata == result2.metadata
    
    def test_dataset_stats_stable(self, executor):
        """Test that dataset stats are stable across calls."""
        result1 = executor.execute("dataset_stats", {}, max_results=1)
        result2 = executor.execute("dataset_stats", {}, max_results=1)
        
        assert result1.results[0]["repo_count"] == result2.results[0]["repo_count"]
        assert result1.results[0]["total_dependencies"] == result2.results[0]["total_dependencies"]


class TestSecurity:
    """Test security features."""
    
    def test_invalid_intent_rejected(self, executor):
        """Test that invalid intents are rejected."""
        with pytest.raises(ValueError, match="Unknown intent"):
            executor.execute(
                intent="DROP TABLE repo_dependencies",
                parameters={},
                max_results=10
            )
    
    def test_sql_injection_in_repo_name(self, executor):
        """Test that SQL injection in repo_full_name is neutralized."""
        result = executor.execute(
            intent="list_dependencies",
            parameters={"repo_full_name": "django/django' OR '1'='1"},
            max_results=10
        )
        
        # Should return 0 results (no repo with that name)
        assert result.result_count == 0
    
    def test_sql_injection_in_package_name(self, executor):
        """Test that SQL injection in package_name is neutralized."""
        result = executor.execute(
            intent="find_dependents",
            parameters={
                "package_name": "flask'; DROP TABLE repo_dependencies; --",
                "registry_type": "pypi"
            },
            max_results=10
        )
        
        # Should return 0 results (no package with that name)
        assert result.result_count == 0
    
    def test_sql_injection_in_pattern(self, executor):
        """Test that SQL injection in search pattern is neutralized."""
        result = executor.execute(
            intent="search_repos",
            parameters={"pattern": "%' OR '1'='1"},
            max_results=10
        )
        
        # Should execute safely (parameterized query)
        assert result.result_count >= 0


class TestResultStructure:
    """Test that results have correct structure."""
    
    def test_query_result_structure(self, executor):
        """Test that QueryResult has all required fields."""
        result = executor.execute(
            intent="dataset_stats",
            parameters={},
            max_results=1
        )
        
        assert hasattr(result, "intent")
        assert hasattr(result, "parameters")
        assert hasattr(result, "results")
        assert hasattr(result, "result_count")
        assert hasattr(result, "execution_time_ms")
        assert hasattr(result, "metadata")
        
        assert isinstance(result.intent, str)
        assert isinstance(result.parameters, dict)
        assert isinstance(result.results, list)
        assert isinstance(result.result_count, int)
        assert isinstance(result.execution_time_ms, float)
    
    def test_results_are_dicts(self, executor):
        """Test that all results are dictionaries."""
        result = executor.execute(
            intent="list_dependencies",
            parameters={"repo_full_name": "django/django"},
            max_results=5
        )
        
        assert all(isinstance(r, dict) for r in result.results)
    
    def test_max_results_respected(self, executor):
        """Test that max_results limit is respected."""
        result = executor.execute(
            intent="list_dependencies",
            parameters={"repo_full_name": "django/django"},
            max_results=3
        )
        
        assert len(result.results) <= 3


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_nonexistent_repo(self, executor):
        """Test querying a repo that doesn't exist."""
        result = executor.execute(
            intent="list_dependencies",
            parameters={"repo_full_name": "nonexistent/repo"},
            max_results=10
        )
        
        assert result.result_count == 0
        assert result.results == []
    
    def test_nonexistent_package(self, executor):
        """Test querying a package that doesn't exist."""
        result = executor.execute(
            intent="find_dependents",
            parameters={"package_name": "nonexistent-package-xyz", "registry_type": "pypi"},
            max_results=10
        )
        
        assert result.result_count == 0
        assert result.results == []
    
    def test_max_depth_limit(self, executor):
        """Test that max_depth is capped at 5."""
        result = executor.execute(
            intent="get_dependency_tree",
            parameters={"repo_full_name": "pallets/flask", "max_depth": 100},
            max_results=50
        )
        
        # Should be capped at 5
        assert all(r["depth"] <= 5 for r in result.results)
    
    def test_wildcard_pattern_search(self, executor):
        """Test search with wildcard pattern."""
        result = executor.execute(
            intent="search_repos",
            parameters={"pattern": "%"},
            max_results=10
        )
        
        # Wildcard pattern matches all repos
        assert result.result_count > 0


class TestPerformance:
    """Test performance characteristics."""
    
    def test_query_execution_time(self, executor):
        """Test that queries execute quickly."""
        result = executor.execute(
            intent="list_dependencies",
            parameters={"repo_full_name": "django/django"},
            max_results=10
        )
        
        # Should execute in < 100ms on 51-repo dataset
        assert result.execution_time_ms < 100
    
    def test_tree_computation_time(self, executor):
        """Test that tree computation is reasonable."""
        result = executor.execute(
            intent="get_dependency_tree",
            parameters={"repo_full_name": "pallets/flask", "max_depth": 3},
            max_results=100
        )
        
        # Should execute in < 200ms
        assert result.execution_time_ms < 200
