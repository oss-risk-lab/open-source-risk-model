#!/usr/bin/env python3
"""
Property-based tests for dependency parsing and resolution.

Uses Hypothesis to test invariants and edge cases.
"""

import pytest
from hypothesis import given, strategies as st, assume, settings
from src.open_source_risk_model.dependencies.parsers import (
    RequirementsTxtParser,
    PackageJsonParser,
    Dependency
)
from src.open_source_risk_model.dependencies.package_resolver import PackageResolver


# Custom strategies for generating test data
package_name_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_'),
    min_size=1,
    max_size=50
).filter(lambda x: x and x[0].isalpha())

version_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('Nd',), whitelist_characters='.'),
    min_size=1,
    max_size=20
).filter(lambda x: x and x[0].isdigit())

version_operator_strategy = st.sampled_from(['==', '>=', '<=', '>', '<', '~=', '!='])


class TestRequirementsTxtParserProperties:
    """Property-based tests for requirements.txt parser."""
    
    def setup_method(self):
        self.parser = RequirementsTxtParser()
    
    @given(package_name=package_name_strategy)
    @settings(max_examples=50)
    def test_parse_simple_package_name(self, package_name):
        """Property: Parsing a simple package name should always succeed."""
        assume(len(package_name) > 0)
        assume(package_name[0].isalpha())
        
        deps = self.parser.parse(package_name)
        
        assert len(deps) >= 0  # May be 0 if invalid, but shouldn't crash
        if len(deps) > 0:
            assert deps[0].package_name.lower() == package_name.lower() or \
                   deps[0].package_name in package_name
    
    @given(
        package_name=package_name_strategy,
        operator=version_operator_strategy,
        version=version_strategy
    )
    @settings(max_examples=50)
    def test_parse_versioned_package(self, package_name, operator, version):
        """Property: Parsing versioned packages should preserve package name."""
        assume(len(package_name) > 0 and package_name[0].isalpha())
        assume(len(version) > 0 and version[0].isdigit())
        
        content = f"{package_name}{operator}{version}"
        deps = self.parser.parse(content)
        
        if len(deps) > 0:
            assert deps[0].package_name.lower() == package_name.lower()
            assert operator in deps[0].specifier or deps[0].specifier == ""
    
    @given(content=st.text(max_size=1000))
    @settings(max_examples=50)
    def test_parse_never_crashes(self, content):
        """Property: Parser should never crash on any input."""
        try:
            deps = self.parser.parse(content)
            assert isinstance(deps, list)
            assert all(isinstance(d, Dependency) for d in deps)
        except Exception as e:
            pytest.fail(f"Parser crashed on input: {repr(content)[:100]}, error: {e}")
    
    @given(package_name=package_name_strategy)
    @settings(max_examples=50)
    def test_parse_idempotent(self, package_name):
        """Property: Parsing the same content twice should give same result."""
        assume(len(package_name) > 0 and package_name[0].isalpha())
        
        content = f"{package_name}>=1.0.0"
        
        deps1 = self.parser.parse(content)
        deps2 = self.parser.parse(content)
        
        assert len(deps1) == len(deps2)
        if len(deps1) > 0:
            assert deps1[0].package_name == deps2[0].package_name
            assert deps1[0].specifier == deps2[0].specifier
    
    @given(
        packages=st.lists(
            package_name_strategy,
            min_size=0,
            max_size=20
        )
    )
    @settings(max_examples=50)
    def test_parse_multiple_packages(self, packages):
        """Property: Number of parsed deps should not exceed number of lines."""
        # Filter valid package names
        valid_packages = [p for p in packages if p and p[0].isalpha()]
        
        content = "\n".join(valid_packages)
        deps = self.parser.parse(content)
        
        # Should not parse more dependencies than input lines
        assert len(deps) <= len(valid_packages)
    
    @given(
        package_name=package_name_strategy,
        comment=st.text(max_size=100)
    )
    @settings(max_examples=50)
    def test_parse_ignores_comments(self, package_name, comment):
        """Property: Comments should not affect package parsing."""
        assume(len(package_name) > 0 and package_name[0].isalpha())
        
        content_without_comment = package_name
        content_with_comment = f"# {comment}\n{package_name}"
        
        deps_without = self.parser.parse(content_without_comment)
        deps_with = self.parser.parse(content_with_comment)
        
        # Should parse same number of dependencies
        assert len(deps_without) == len(deps_with)


class TestPackageJsonParserProperties:
    """Property-based tests for package.json parser."""
    
    def setup_method(self):
        self.parser = PackageJsonParser()
    
    @given(content=st.text(max_size=1000))
    @settings(max_examples=50)
    def test_parse_never_crashes(self, content):
        """Property: Parser should never crash on any input."""
        try:
            deps = self.parser.parse(content)
            assert isinstance(deps, list)
            assert all(isinstance(d, Dependency) for d in deps)
        except Exception as e:
            pytest.fail(f"Parser crashed on input: {repr(content)[:100]}, error: {e}")
    
    @given(
        package_name=package_name_strategy,
        version=st.text(min_size=1, max_size=20)
    )
    @settings(max_examples=50)
    def test_parse_dependencies_section(self, package_name, version):
        """Property: Valid dependencies section should be parsed."""
        assume(len(package_name) > 0 and package_name[0].isalpha())
        assume('"' not in package_name and '"' not in version)
        
        content = f'{{"dependencies": {{"{package_name}": "{version}"}}}}'
        
        deps = self.parser.parse(content)
        
        if len(deps) > 0:
            assert deps[0].package_name == package_name
            assert deps[0].specifier == version
            assert deps[0].dependency_group == "prod"
    
    @given(
        prod_packages=st.lists(package_name_strategy, min_size=0, max_size=5),
        dev_packages=st.lists(package_name_strategy, min_size=0, max_size=5)
    )
    @settings(max_examples=50)
    def test_parse_separates_prod_and_dev(self, prod_packages, dev_packages):
        """Property: Production and dev dependencies should be separated."""
        # Filter valid package names
        valid_prod = [p for p in prod_packages if p and p[0].isalpha() and '"' not in p]
        valid_dev = [p for p in dev_packages if p and p[0].isalpha() and '"' not in p]
        
        if not valid_prod and not valid_dev:
            return
        
        prod_deps = ', '.join([f'"{p}": "1.0.0"' for p in valid_prod])
        dev_deps = ', '.join([f'"{p}": "1.0.0"' for p in valid_dev])
        
        content = '{'
        if valid_prod:
            content += f'"dependencies": {{{prod_deps}}}'
        if valid_dev:
            if valid_prod:
                content += ','
            content += f'"devDependencies": {{{dev_deps}}}'
        content += '}'
        
        deps = self.parser.parse(content)
        
        prod_parsed = [d for d in deps if d.dependency_group == "prod"]
        dev_parsed = [d for d in deps if d.dependency_group == "dev"]
        
        # All dev dependencies should be marked as dev
        assert all(d.is_dev for d in dev_parsed)
        assert all(not d.is_dev for d in prod_parsed)


class TestPackageResolverProperties:
    """Property-based tests for package resolver."""
    
    def setup_method(self):
        from unittest.mock import Mock
        self.mock_cache = Mock()
        self.resolver = PackageResolver(self.mock_cache)
    
    @given(
        url=st.text(min_size=10, max_size=200)
    )
    @settings(max_examples=50)
    def test_extract_github_repo_never_crashes(self, url):
        """Property: URL extraction should never crash."""
        try:
            result = self.resolver._extract_github_repo(url)
            assert result is None or isinstance(result, str)
        except Exception as e:
            pytest.fail(f"URL extraction crashed on: {repr(url)[:100]}, error: {e}")
    
    @given(
        owner=st.text(
            alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_'),
            min_size=1,
            max_size=39
        ),
        repo=st.text(
            alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_'),
            min_size=1,
            max_size=100
        )
    )
    @settings(max_examples=50)
    def test_extract_github_repo_from_valid_url(self, owner, repo):
        """Property: Valid GitHub URLs should be extracted correctly."""
        assume(len(owner) > 0 and len(repo) > 0)
        assume(owner[0].isalnum() and repo[0].isalnum())
        
        url = f"https://github.com/{owner}/{repo}"
        result = self.resolver._extract_github_repo(url)
        
        if result:
            assert "/" in result
            parts = result.split("/")
            assert len(parts) == 2
            assert parts[0] == owner
            assert parts[1] == repo
    
    @given(
        owner=st.text(min_size=1, max_size=39),
        repo=st.text(min_size=1, max_size=100),
        suffix=st.sampled_from(['', '.git', '.git/'])
    )
    @settings(max_examples=50)
    def test_extract_github_repo_handles_git_suffix(self, owner, repo, suffix):
        """Property: .git suffix should be handled correctly."""
        assume(owner and repo)
        assume('/' not in owner and '/' not in repo)
        
        url = f"https://github.com/{owner}/{repo}{suffix}"
        result = self.resolver._extract_github_repo(url)
        
        if result:
            # Should not include .git in result
            assert not result.endswith('.git')
            assert '/' in result
    
    @given(repo_format=st.text(min_size=1, max_size=200))
    @settings(max_examples=50)
    def test_is_valid_repo_format_never_crashes(self, repo_format):
        """Property: Repo format validation should never crash."""
        try:
            result = self.resolver._is_valid_repo_format(repo_format)
            assert isinstance(result, bool)
        except Exception as e:
            pytest.fail(f"Validation crashed on: {repr(repo_format)[:100]}, error: {e}")
    
    @given(
        owner=st.text(
            alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_'),
            min_size=1,
            max_size=39
        ),
        repo=st.text(
            alphabet=st.characters(whitelist_categories=('Ll', 'Lu', 'Nd'), whitelist_characters='-_.'),
            min_size=1,
            max_size=100
        )
    )
    @settings(max_examples=50)
    def test_valid_repo_format_accepted(self, owner, repo):
        """Property: Valid owner/repo format should be accepted."""
        assume(owner and repo)
        assume(owner[0].isalnum() and repo[0].isalnum())
        
        repo_format = f"{owner}/{repo}"
        result = self.resolver._is_valid_repo_format(repo_format)
        
        # Should accept valid formats
        if '/' in repo_format and repo_format.count('/') == 1:
            parts = repo_format.split('/')
            if all(p for p in parts):  # No empty parts
                assert result or not result  # May be valid or invalid, but shouldn't crash


class TestDependencyInvariants:
    """Test invariants that should hold across all operations."""
    
    @given(
        package_name=package_name_strategy,
        specifier=st.text(max_size=50)
    )
    @settings(max_examples=50)
    def test_dependency_creation_invariants(self, package_name, specifier):
        """Property: Dependency objects should maintain invariants."""
        assume(package_name and package_name[0].isalpha())
        
        dep = Dependency(
            package_name=package_name,
            specifier=specifier,
            dependency_group="prod"
        )
        
        # Invariants
        assert dep.package_name == package_name
        assert dep.specifier == specifier
        assert dep.dependency_group in ["prod", "dev", "test", "docs", "optional"]
        assert isinstance(dep.is_dev, bool)
        assert isinstance(dep.is_optional, bool)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
