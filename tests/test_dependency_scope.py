"""
Tests for dependency scope filtering.
"""

import pytest
from open_source_risk_model.query.dependency_scope import (
    DependencyScope,
    filter_dependencies_by_scope,
    get_scope_description,
    PROD_GROUPS,
    BUILD_GROUPS,
    OPTIONAL_GROUPS
)


class TestDependencyScopeEnum:
    """Test DependencyScope enum."""
    
    def test_scope_values(self):
        """Test that scope enum has expected values."""
        assert DependencyScope.PROD == "prod"
        assert DependencyScope.BUILD == "build"
        assert DependencyScope.ALL == "all"
    
    def test_scope_from_string(self):
        """Test creating scope from string."""
        assert DependencyScope("prod") == DependencyScope.PROD
        assert DependencyScope("build") == DependencyScope.BUILD
        assert DependencyScope("all") == DependencyScope.ALL
    
    def test_invalid_scope_raises(self):
        """Test that invalid scope raises ValueError."""
        with pytest.raises(ValueError):
            DependencyScope("invalid")


class TestScopeDescriptions:
    """Test scope descriptions."""
    
    def test_prod_description(self):
        """Test production scope description."""
        desc = get_scope_description(DependencyScope.PROD)
        assert "production" in desc.lower() or "runtime" in desc.lower()
    
    def test_build_description(self):
        """Test build scope description."""
        desc = get_scope_description(DependencyScope.BUILD)
        assert "build" in desc.lower() or "dev" in desc.lower()
    
    def test_all_description(self):
        """Test all scope description."""
        desc = get_scope_description(DependencyScope.ALL)
        assert "all" in desc.lower()


class TestScopeFiltering:
    """Test dependency scope filtering logic."""
    
    def test_all_scope_returns_everything(self):
        """Test that 'all' scope returns all dependencies."""
        deps = [
            {"package_name": "prod-dep", "dependency_group": "prod", "is_optional": 0},
            {"package_name": "dev-dep", "dependency_group": "dev", "is_optional": 0},
            {"package_name": "optional-dep", "dependency_group": "async", "is_optional": 1},
        ]
        
        result = filter_dependencies_by_scope(deps, DependencyScope.ALL)
        assert len(result) == 3
    
    def test_prod_scope_excludes_dev(self):
        """Test that 'prod' scope excludes dev dependencies."""
        deps = [
            {"package_name": "prod-dep", "dependency_group": "prod", "is_optional": 0},
            {"package_name": "dev-dep", "dependency_group": "dev", "is_optional": 0},
        ]
        
        result = filter_dependencies_by_scope(deps, DependencyScope.PROD)
        assert len(result) == 1
        assert result[0]["package_name"] == "prod-dep"
    
    def test_prod_scope_excludes_optional(self):
        """Test that 'prod' scope excludes optional dependencies."""
        deps = [
            {"package_name": "prod-dep", "dependency_group": "prod", "is_optional": 0},
            {"package_name": "optional-dep", "dependency_group": "async", "is_optional": 1},
        ]
        
        result = filter_dependencies_by_scope(deps, DependencyScope.PROD)
        assert len(result) == 1
        assert result[0]["package_name"] == "prod-dep"
    
    def test_build_scope_includes_dev(self):
        """Test that 'build' scope includes dev dependencies."""
        deps = [
            {"package_name": "prod-dep", "dependency_group": "prod", "is_optional": 0},
            {"package_name": "dev-dep", "dependency_group": "dev", "is_optional": 0},
        ]
        
        result = filter_dependencies_by_scope(deps, DependencyScope.BUILD)
        assert len(result) == 2
    
    def test_build_scope_excludes_optional(self):
        """Test that 'build' scope excludes optional extras."""
        deps = [
            {"package_name": "prod-dep", "dependency_group": "prod", "is_optional": 0},
            {"package_name": "dev-dep", "dependency_group": "dev", "is_optional": 0},
            {"package_name": "optional-dep", "dependency_group": "async", "is_optional": 1},
        ]
        
        result = filter_dependencies_by_scope(deps, DependencyScope.BUILD)
        assert len(result) == 2
        assert all(d["package_name"] != "optional-dep" for d in result)
    
    def test_prod_subset_of_build(self):
        """Test that prod scope is a subset of build scope."""
        deps = [
            {"package_name": "prod-dep", "dependency_group": "prod", "is_optional": 0},
            {"package_name": "dev-dep", "dependency_group": "dev", "is_optional": 0},
            {"package_name": "test-dep", "dependency_group": "test", "is_optional": 0},
        ]
        
        prod_result = filter_dependencies_by_scope(deps, DependencyScope.PROD)
        build_result = filter_dependencies_by_scope(deps, DependencyScope.BUILD)
        
        assert len(prod_result) < len(build_result)
        prod_names = {d["package_name"] for d in prod_result}
        build_names = {d["package_name"] for d in build_result}
        assert prod_names.issubset(build_names)
    
    def test_build_subset_of_all(self):
        """Test that build scope is a subset of all scope."""
        deps = [
            {"package_name": "prod-dep", "dependency_group": "prod", "is_optional": 0},
            {"package_name": "dev-dep", "dependency_group": "dev", "is_optional": 0},
            {"package_name": "optional-dep", "dependency_group": "async", "is_optional": 1},
        ]
        
        build_result = filter_dependencies_by_scope(deps, DependencyScope.BUILD)
        all_result = filter_dependencies_by_scope(deps, DependencyScope.ALL)
        
        assert len(build_result) < len(all_result)
        build_names = {d["package_name"] for d in build_result}
        all_names = {d["package_name"] for d in all_result}
        assert build_names.issubset(all_names)
    
    def test_empty_dependency_group(self):
        """Test handling of empty/None dependency_group."""
        deps = [
            {"package_name": "dep1", "dependency_group": "", "is_optional": 0},
            {"package_name": "dep2", "dependency_group": None, "is_optional": 0},
        ]
        
        # Empty group should be treated as prod
        result = filter_dependencies_by_scope(deps, DependencyScope.PROD)
        assert len(result) == 2
    
    def test_peer_dependencies_included_in_prod(self):
        """Test that peer dependencies are included in prod scope."""
        deps = [
            {"package_name": "peer-dep", "dependency_group": "peer", "is_optional": 0},
        ]
        
        result = filter_dependencies_by_scope(deps, DependencyScope.PROD)
        assert len(result) == 1
    
    def test_standard_group_included_in_prod(self):
        """Test that 'standard' group is included in prod scope."""
        deps = [
            {"package_name": "std-dep", "dependency_group": "standard", "is_optional": 0},
        ]
        
        result = filter_dependencies_by_scope(deps, DependencyScope.PROD)
        assert len(result) == 1
    
    def test_test_group_excluded_from_prod(self):
        """Test that 'test' group is excluded from prod scope."""
        deps = [
            {"package_name": "test-dep", "dependency_group": "test", "is_optional": 0},
        ]
        
        result = filter_dependencies_by_scope(deps, DependencyScope.PROD)
        assert len(result) == 0
    
    def test_test_group_included_in_build(self):
        """Test that 'test' group is included in build scope."""
        deps = [
            {"package_name": "test-dep", "dependency_group": "test", "is_optional": 0},
        ]
        
        result = filter_dependencies_by_scope(deps, DependencyScope.BUILD)
        assert len(result) == 1
    
    def test_optional_extras_by_group_name(self):
        """Test that optional extras are identified by group name."""
        optional_groups = ["async", "dotenv", "speedups", "cli"]
        
        for group in optional_groups:
            deps = [
                {"package_name": f"{group}-dep", "dependency_group": group, "is_optional": 0},
            ]
            
            # Should be excluded from prod
            prod_result = filter_dependencies_by_scope(deps, DependencyScope.PROD)
            assert len(prod_result) == 0, f"{group} should be excluded from prod"
            
            # Should be excluded from build
            build_result = filter_dependencies_by_scope(deps, DependencyScope.BUILD)
            assert len(build_result) == 0, f"{group} should be excluded from build"
            
            # Should be included in all
            all_result = filter_dependencies_by_scope(deps, DependencyScope.ALL)
            assert len(all_result) == 1, f"{group} should be included in all"
    
    def test_is_optional_flag_respected(self):
        """Test that is_optional=1 flag is respected."""
        deps = [
            {"package_name": "optional-dep", "dependency_group": "prod", "is_optional": 1},
        ]
        
        # Should be excluded from prod even if group is "prod"
        prod_result = filter_dependencies_by_scope(deps, DependencyScope.PROD)
        assert len(prod_result) == 0
        
        # Should be excluded from build
        build_result = filter_dependencies_by_scope(deps, DependencyScope.BUILD)
        assert len(build_result) == 0
        
        # Should be included in all
        all_result = filter_dependencies_by_scope(deps, DependencyScope.ALL)
        assert len(all_result) == 1
    
    def test_case_insensitive_group_matching(self):
        """Test that group matching is case-insensitive."""
        deps = [
            {"package_name": "dep1", "dependency_group": "PROD", "is_optional": 0},
            {"package_name": "dep2", "dependency_group": "Dev", "is_optional": 0},
        ]
        
        prod_result = filter_dependencies_by_scope(deps, DependencyScope.PROD)
        assert len(prod_result) == 1
        assert prod_result[0]["package_name"] == "dep1"
        
        build_result = filter_dependencies_by_scope(deps, DependencyScope.BUILD)
        assert len(build_result) == 2


class TestGroupDefinitions:
    """Test that group definitions are sensible."""
    
    def test_no_overlap_between_prod_and_build(self):
        """Test that prod and build groups don't overlap."""
        overlap = PROD_GROUPS & BUILD_GROUPS
        assert len(overlap) == 0, f"Prod and build groups should not overlap: {overlap}"
    
    def test_no_overlap_between_prod_and_optional(self):
        """Test that prod and optional groups don't overlap."""
        overlap = PROD_GROUPS & OPTIONAL_GROUPS
        assert len(overlap) == 0, f"Prod and optional groups should not overlap: {overlap}"
    
    def test_no_overlap_between_build_and_optional(self):
        """Test that build and optional groups don't overlap."""
        overlap = BUILD_GROUPS & OPTIONAL_GROUPS
        assert len(overlap) == 0, f"Build and optional groups should not overlap: {overlap}"
    
    def test_prod_groups_defined(self):
        """Test that prod groups are defined."""
        assert len(PROD_GROUPS) > 0
        assert "prod" in PROD_GROUPS
    
    def test_build_groups_defined(self):
        """Test that build groups are defined."""
        assert len(BUILD_GROUPS) > 0
        assert "dev" in BUILD_GROUPS
        assert "test" in BUILD_GROUPS
    
    def test_optional_groups_defined(self):
        """Test that optional groups are defined."""
        assert len(OPTIONAL_GROUPS) > 0
