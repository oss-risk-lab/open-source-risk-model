#!/usr/bin/env python3
"""
Unit tests for dependency parsers.

Tests all parser implementations for correctness, edge cases, and error handling.
"""

import pytest
from src.open_source_risk_model.dependencies.parsers import (
    RequirementsTxtParser,
    PyProjectTomlParser,
    PackageJsonParser,
    DependencyParserRegistry,
    Dependency
)


class TestRequirementsTxtParser:
    """Test requirements.txt parser."""
    
    def setup_method(self):
        self.parser = RequirementsTxtParser()
    
    def test_can_parse_requirements_txt(self):
        """Test file detection."""
        assert self.parser.can_parse("requirements.txt")
        assert self.parser.can_parse("requirements.in")
        assert self.parser.can_parse("requirements-dev.txt")
        assert not self.parser.can_parse("package.json")
    
    def test_parse_simple_package(self):
        """Test parsing simple package name."""
        content = "requests"
        deps = self.parser.parse(content)
        
        assert len(deps) == 1
        assert deps[0].package_name == "requests"
        assert deps[0].specifier == ""
        assert not deps[0].is_dev
    
    def test_parse_versioned_package(self):
        """Test parsing package with version."""
        content = "requests==2.31.0"
        deps = self.parser.parse(content)
        
        assert len(deps) == 1
        assert deps[0].package_name == "requests"
        assert deps[0].specifier == "==2.31.0"
    
    def test_parse_version_constraints(self):
        """Test parsing various version constraints."""
        content = """
requests>=2.0.0
flask<3.0.0
django>=3.0,<4.0
numpy~=1.20.0
"""
        deps = self.parser.parse(content)
        
        assert len(deps) == 4
        assert deps[0].specifier == ">=2.0.0"
        assert deps[1].specifier == "<3.0.0"
        assert deps[2].specifier == ">=3.0,<4.0"
        assert deps[3].specifier == "~=1.20.0"
    
    def test_parse_with_extras(self):
        """Test parsing packages with extras."""
        content = "requests[security,socks]"
        deps = self.parser.parse(content)
        
        assert len(deps) == 1
        assert deps[0].package_name == "requests"
        assert deps[0].extras == ["security", "socks"]
    
    def test_parse_with_environment_markers(self):
        """Test parsing packages with environment markers."""
        content = 'requests>=2.0.0; python_version >= "3.7"'
        deps = self.parser.parse(content)
        
        assert len(deps) == 1
        assert deps[0].package_name == "requests"
        assert deps[0].specifier == ">=2.0.0"
        assert 'python_version >= "3.7"' in deps[0].markers
    
    def test_parse_skip_comments(self):
        """Test that comments are skipped."""
        content = """
# This is a comment
requests==2.31.0
# Another comment
flask>=2.0.0
"""
        deps = self.parser.parse(content)
        
        assert len(deps) == 2
        assert deps[0].package_name == "requests"
        assert deps[1].package_name == "flask"
    
    def test_parse_skip_empty_lines(self):
        """Test that empty lines are skipped."""
        content = """
requests==2.31.0

flask>=2.0.0

"""
        deps = self.parser.parse(content)
        
        assert len(deps) == 2
    
    def test_parse_skip_flags(self):
        """Test that pip flags are skipped."""
        content = """
-r requirements-base.txt
-e git+https://github.com/user/repo.git
--index-url https://pypi.org/simple
requests==2.31.0
"""
        deps = self.parser.parse(content)
        
        assert len(deps) == 1
        assert deps[0].package_name == "requests"
    
    def test_parse_complex_file(self):
        """Test parsing a complex requirements file."""
        content = """
# Production dependencies
requests>=2.31.0
flask[async]>=2.3.0,<3.0.0
django~=4.2.0

# Database
psycopg2-binary==2.9.6; sys_platform != 'win32'

# Utilities
python-dotenv>=1.0.0
"""
        deps = self.parser.parse(content)
        
        assert len(deps) == 5
        assert deps[0].package_name == "requests"
        assert deps[1].package_name == "flask"
        assert deps[1].extras == ["async"]
        assert deps[2].package_name == "django"
        assert deps[3].package_name == "psycopg2-binary"
        assert deps[4].package_name == "python-dotenv"
    
    def test_parse_empty_file(self):
        """Test parsing empty file."""
        content = ""
        deps = self.parser.parse(content)
        
        assert len(deps) == 0
    
    def test_parse_malformed_lines(self):
        """Test that malformed lines are skipped gracefully."""
        content = """
requests==2.31.0
this is not a valid line
flask>=2.0.0
"""
        deps = self.parser.parse(content)
        
        # Should parse valid lines and skip invalid ones
        assert len(deps) >= 2


class TestPyProjectTomlParser:
    """Test pyproject.toml parser."""
    
    def setup_method(self):
        self.parser = PyProjectTomlParser()
    
    def test_can_parse_pyproject_toml(self):
        """Test file detection."""
        assert self.parser.can_parse("pyproject.toml")
        assert not self.parser.can_parse("requirements.txt")
    
    def test_parse_pep621_dependencies(self):
        """Test parsing PEP 621 dependencies."""
        content = """
[project]
name = "myproject"
dependencies = [
    "requests>=2.31.0",
    "flask<3.0.0",
]
"""
        deps = self.parser.parse(content)
        
        assert len(deps) == 2
        assert deps[0].package_name == "requests"
        assert deps[0].specifier == ">=2.31.0"
        assert deps[1].package_name == "flask"
    
    def test_parse_pep621_optional_dependencies(self):
        """Test parsing optional dependencies."""
        content = """
[project]
dependencies = ["requests"]

[project.optional-dependencies]
dev = ["pytest>=7.0.0", "black"]
docs = ["sphinx"]
"""
        deps = self.parser.parse(content)
        
        # Should include all dependencies
        assert len(deps) == 4
        
        # Check dependency groups
        prod_deps = [d for d in deps if d.dependency_group == "prod"]
        dev_deps = [d for d in deps if d.dependency_group == "dev"]
        docs_deps = [d for d in deps if d.dependency_group == "docs"]
        
        assert len(prod_deps) == 1
        assert len(dev_deps) == 2
        assert len(docs_deps) == 1
    
    def test_parse_poetry_dependencies(self):
        """Test parsing Poetry dependencies."""
        content = """
[tool.poetry.dependencies]
python = "^3.8"
requests = "^2.31.0"
flask = {version = ">=2.0.0", optional = true}

[tool.poetry.dev-dependencies]
pytest = "^7.0.0"
"""
        deps = self.parser.parse(content)
        
        # Should parse both regular and dev dependencies
        assert len(deps) >= 2
        
        # Check for requests
        requests_dep = next(d for d in deps if d.package_name == "requests")
        assert requests_dep.specifier == "^2.31.0"
    
    def test_parse_empty_file(self):
        """Test parsing empty file."""
        content = ""
        deps = self.parser.parse(content)
        
        assert len(deps) == 0
    
    def test_parse_malformed_toml(self):
        """Test that malformed TOML returns empty list."""
        content = "this is not valid TOML [[[["
        deps = self.parser.parse(content)
        
        assert len(deps) == 0


class TestPackageJsonParser:
    """Test package.json parser."""
    
    def setup_method(self):
        self.parser = PackageJsonParser()
    
    def test_can_parse_package_json(self):
        """Test file detection."""
        assert self.parser.can_parse("package.json")
        assert not self.parser.can_parse("requirements.txt")
    
    def test_parse_dependencies(self):
        """Test parsing production dependencies."""
        content = """
{
  "name": "myproject",
  "dependencies": {
    "react": "^18.2.0",
    "express": "~4.18.0"
  }
}
"""
        deps = self.parser.parse(content)
        
        assert len(deps) == 2
        assert deps[0].package_name == "react"
        assert deps[0].specifier == "^18.2.0"
        assert deps[0].dependency_group == "prod"
        assert not deps[0].is_dev
    
    def test_parse_dev_dependencies(self):
        """Test parsing dev dependencies."""
        content = """
{
  "dependencies": {
    "react": "^18.2.0"
  },
  "devDependencies": {
    "jest": "^29.0.0",
    "eslint": "^8.0.0"
  }
}
"""
        deps = self.parser.parse(content)
        
        assert len(deps) == 3
        
        prod_deps = [d for d in deps if d.dependency_group == "prod"]
        dev_deps = [d for d in deps if d.dependency_group == "dev"]
        
        assert len(prod_deps) == 1
        assert len(dev_deps) == 2
        assert dev_deps[0].is_dev
    
    def test_parse_optional_dependencies(self):
        """Test parsing optional dependencies."""
        content = """
{
  "dependencies": {
    "react": "^18.2.0"
  },
  "optionalDependencies": {
    "fsevents": "^2.3.0"
  }
}
"""
        deps = self.parser.parse(content)
        
        assert len(deps) == 2
        
        optional_dep = next(d for d in deps if d.package_name == "fsevents")
        assert optional_dep.is_optional
    
    def test_parse_empty_dependencies(self):
        """Test parsing package.json with no dependencies."""
        content = """
{
  "name": "myproject",
  "version": "1.0.0"
}
"""
        deps = self.parser.parse(content)
        
        assert len(deps) == 0
    
    def test_parse_malformed_json(self):
        """Test that malformed JSON returns empty list."""
        content = "{ this is not valid JSON"
        deps = self.parser.parse(content)
        
        assert len(deps) == 0


class TestDependencyParserRegistry:
    """Test parser registry."""
    
    def setup_method(self):
        self.registry = DependencyParserRegistry()
    
    def test_get_parser_for_requirements_txt(self):
        """Test getting parser for requirements.txt."""
        parser = self.registry.get_parser("requirements.txt")
        
        assert parser is not None
        assert isinstance(parser, RequirementsTxtParser)
    
    def test_get_parser_for_pyproject_toml(self):
        """Test getting parser for pyproject.toml."""
        parser = self.registry.get_parser("pyproject.toml")
        
        assert parser is not None
        assert isinstance(parser, PyProjectTomlParser)
    
    def test_get_parser_for_package_json(self):
        """Test getting parser for package.json."""
        parser = self.registry.get_parser("package.json")
        
        assert parser is not None
        assert isinstance(parser, PackageJsonParser)
    
    def test_get_parser_for_unknown_file(self):
        """Test getting parser for unknown file type."""
        parser = self.registry.get_parser("unknown.txt")
        
        assert parser is None
    
    def test_parse_file_requirements_txt(self):
        """Test parsing file through registry."""
        content = "requests==2.31.0\nflask>=2.0.0"
        deps = self.registry.parse_file("requirements.txt", content)
        
        assert len(deps) == 2
        assert deps[0].package_name == "requests"
    
    def test_parse_file_unknown_type(self):
        """Test parsing unknown file type."""
        content = "some content"
        deps = self.registry.parse_file("unknown.txt", content)
        
        assert len(deps) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
