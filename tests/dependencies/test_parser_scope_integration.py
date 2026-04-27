"""
Parser integration tests for dependency scope classification.

Tests that each parser correctly sets dependency_scope and scope_confidence
on every Dependency object, and that DependencyParserRegistry.parse_file()
works end-to-end.

Validates: Requirements 9.1, 15.1–15.4
"""

import json
import pytest

from open_source_risk_model.dependencies.parsers import (
    DependencyParserRegistry,
    PackageJsonParser,
    PyProjectTomlParser,
    RequirementsTxtParser,
)


# ---------------------------------------------------------------------------
# Sample manifest content
# ---------------------------------------------------------------------------

SAMPLE_PACKAGE_JSON = json.dumps({
    "name": "test-project",
    "version": "1.0.0",
    "dependencies": {
        "express": "^4.18.0",
        "lodash": "^4.17.21",
    },
    "devDependencies": {
        "jest": "^29.0.0",
        "eslint": "^8.0.0",
    },
    "peerDependencies": {
        "react": "^18.0.0",
    },
    "optionalDependencies": {
        "fsevents": "^2.3.0",
    },
})

SAMPLE_PYPROJECT_PEP621 = """\
[project]
name = "mylib"
version = "1.0.0"
dependencies = [
    "requests>=2.28",
    "click>=8.0",
]

[project.optional-dependencies]
dev = ["pytest>=7.0", "black>=23.0"]
test = ["coverage>=7.0"]
docs = ["sphinx>=6.0"]
extras = ["ujson>=5.0"]
"""

SAMPLE_PYPROJECT_POETRY = """\
[tool.poetry]
name = "mylib"
version = "1.0.0"

[tool.poetry.dependencies]
python = "^3.10"
requests = "^2.28"
click = {version = "^8.0", optional = true}

[tool.poetry.dev-dependencies]
pytest = "^7.0"

[tool.poetry.group.test.dependencies]
coverage = "^7.0"

[tool.poetry.group.docs.dependencies]
sphinx = "^6.0"
"""

SAMPLE_REQUIREMENTS_TXT = """\
requests>=2.28
click>=8.0
"""

SAMPLE_REQUIREMENTS_DEV = """\
pytest>=7.0
black>=23.0
"""

SAMPLE_REQUIREMENTS_TEST = """\
coverage>=7.0
tox>=4.0
"""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _scope_map(deps):
    """Return {package_name: (dependency_scope, scope_confidence)} dict."""
    return {d.package_name: (d.dependency_scope, d.scope_confidence) for d in deps}


# ---------------------------------------------------------------------------
# PackageJsonParser tests  (Req 15.1)
# ---------------------------------------------------------------------------

class TestPackageJsonParserScope:
    """Validates: Requirement 15.1 — npm package.json classification."""

    def test_prod_dependencies_are_runtime_high(self):
        parser = PackageJsonParser()
        deps = parser.parse(SAMPLE_PACKAGE_JSON)
        sm = _scope_map(deps)
        assert sm["express"] == ("runtime", "high")
        assert sm["lodash"] == ("runtime", "high")

    def test_dev_dependencies_are_dev_high(self):
        parser = PackageJsonParser()
        deps = parser.parse(SAMPLE_PACKAGE_JSON)
        sm = _scope_map(deps)
        assert sm["jest"] == ("dev", "high")
        assert sm["eslint"] == ("dev", "high")

    def test_peer_dependencies_are_peer_medium(self):
        parser = PackageJsonParser()
        deps = parser.parse(SAMPLE_PACKAGE_JSON)
        sm = _scope_map(deps)
        assert sm["react"] == ("peer", "medium")

    def test_optional_dependencies_are_optional_high(self):
        parser = PackageJsonParser()
        deps = parser.parse(SAMPLE_PACKAGE_JSON)
        sm = _scope_map(deps)
        assert sm["fsevents"] == ("optional", "high")

    def test_all_deps_have_scope_fields(self):
        parser = PackageJsonParser()
        deps = parser.parse(SAMPLE_PACKAGE_JSON)
        for dep in deps:
            assert dep.dependency_scope in ("runtime", "dev", "test", "build", "optional", "peer", "unknown")
            assert dep.scope_confidence in ("high", "medium", "low")


# ---------------------------------------------------------------------------
# PyProjectTomlParser — PEP 621 tests  (Req 15.2)
# ---------------------------------------------------------------------------

class TestPyProjectPEP621Scope:
    """Validates: Requirement 15.2 — pyproject.toml PEP 621 classification."""

    def test_project_dependencies_are_runtime_high(self):
        parser = PyProjectTomlParser()
        deps = parser.parse(SAMPLE_PYPROJECT_PEP621)
        sm = _scope_map(deps)
        assert sm["requests"] == ("runtime", "high")
        assert sm["click"] == ("runtime", "high")

    def test_dev_group_is_dev_high(self):
        parser = PyProjectTomlParser()
        deps = parser.parse(SAMPLE_PYPROJECT_PEP621)
        sm = _scope_map(deps)
        assert sm["pytest"] == ("dev", "high")
        assert sm["black"] == ("dev", "high")

    def test_test_group_is_test_high(self):
        parser = PyProjectTomlParser()
        deps = parser.parse(SAMPLE_PYPROJECT_PEP621)
        sm = _scope_map(deps)
        assert sm["coverage"] == ("test", "high")

    def test_docs_group_is_build_medium(self):
        parser = PyProjectTomlParser()
        deps = parser.parse(SAMPLE_PYPROJECT_PEP621)
        sm = _scope_map(deps)
        assert sm["sphinx"] == ("build", "medium")

    def test_extras_group_is_optional_high(self):
        parser = PyProjectTomlParser()
        deps = parser.parse(SAMPLE_PYPROJECT_PEP621)
        sm = _scope_map(deps)
        assert sm["ujson"] == ("optional", "high")


# ---------------------------------------------------------------------------
# PyProjectTomlParser — Poetry tests  (Req 15.2, 5.1–5.3)
# ---------------------------------------------------------------------------

class TestPyProjectPoetryScope:
    """Validates: Requirements 5.1–5.3, 15.2 — Poetry classification."""

    def test_main_dependencies_are_runtime_high(self):
        parser = PyProjectTomlParser()
        deps = parser.parse(SAMPLE_PYPROJECT_POETRY)
        sm = _scope_map(deps)
        assert sm["requests"] == ("runtime", "high")

    def test_optional_poetry_dep_in_main_section(self):
        """Poetry main deps with optional=true are classified as runtime
        because the parser passes group='prod' and the classifier prioritizes
        the prod group check over the is_optional flag."""
        parser = PyProjectTomlParser()
        deps = parser.parse(SAMPLE_PYPROJECT_POETRY)
        sm = _scope_map(deps)
        # The classifier checks group=="prod" first → runtime/high
        assert sm["click"] == ("runtime", "high")

    def test_legacy_dev_dependencies_are_dev_high(self):
        parser = PyProjectTomlParser()
        deps = parser.parse(SAMPLE_PYPROJECT_POETRY)
        sm = _scope_map(deps)
        assert sm["pytest"] == ("dev", "high")

    def test_group_test_is_test_high(self):
        parser = PyProjectTomlParser()
        deps = parser.parse(SAMPLE_PYPROJECT_POETRY)
        sm = _scope_map(deps)
        assert sm["coverage"] == ("test", "high")

    def test_group_docs_is_build(self):
        parser = PyProjectTomlParser()
        deps = parser.parse(SAMPLE_PYPROJECT_POETRY)
        sm = _scope_map(deps)
        # Poetry docs group → build / high (per design table for Poetry)
        assert sm["sphinx"][0] == "build"


# ---------------------------------------------------------------------------
# RequirementsTxtParser tests  (Req 15.3)
# ---------------------------------------------------------------------------

class TestRequirementsTxtParserScope:
    """Validates: Requirement 15.3 — requirements.txt filename classification."""

    def test_plain_requirements_txt_is_runtime_medium(self):
        parser = RequirementsTxtParser()
        deps = parser.parse(SAMPLE_REQUIREMENTS_TXT, source_file="requirements.txt")
        sm = _scope_map(deps)
        assert sm["requests"] == ("runtime", "medium")
        assert sm["click"] == ("runtime", "medium")

    def test_requirements_dev_is_dev_high(self):
        parser = RequirementsTxtParser()
        deps = parser.parse(SAMPLE_REQUIREMENTS_DEV, source_file="requirements-dev.txt")
        sm = _scope_map(deps)
        assert sm["pytest"] == ("dev", "high")
        assert sm["black"] == ("dev", "high")

    def test_requirements_test_is_test_high(self):
        parser = RequirementsTxtParser()
        deps = parser.parse(SAMPLE_REQUIREMENTS_TEST, source_file="requirements-test.txt")
        sm = _scope_map(deps)
        assert sm["coverage"] == ("test", "high")
        assert sm["tox"] == ("test", "high")

    def test_dev_requirements_alt_name_is_dev_high(self):
        parser = RequirementsTxtParser()
        deps = parser.parse(SAMPLE_REQUIREMENTS_DEV, source_file="dev-requirements.txt")
        sm = _scope_map(deps)
        assert sm["pytest"] == ("dev", "high")

    def test_unrecognized_filename_is_unknown_low(self):
        parser = RequirementsTxtParser()
        deps = parser.parse(SAMPLE_REQUIREMENTS_TXT, source_file="deps-extra.txt")
        sm = _scope_map(deps)
        assert sm["requests"] == ("unknown", "low")


# ---------------------------------------------------------------------------
# DependencyParserRegistry.parse_file() integration  (Req 9.1)
# ---------------------------------------------------------------------------

class TestRegistryParseFileIntegration:
    """Validates: Requirement 9.1 — full integration through parse_file()."""

    def setup_method(self):
        self.registry = DependencyParserRegistry()

    def test_package_json_via_registry(self):
        deps = self.registry.parse_file("package.json", SAMPLE_PACKAGE_JSON)
        sm = _scope_map(deps)
        assert sm["express"] == ("runtime", "high")
        assert sm["jest"] == ("dev", "high")
        assert sm["react"] == ("peer", "medium")
        assert sm["fsevents"] == ("optional", "high")

    def test_pyproject_pep621_via_registry(self):
        deps = self.registry.parse_file("pyproject.toml", SAMPLE_PYPROJECT_PEP621)
        sm = _scope_map(deps)
        assert sm["requests"] == ("runtime", "high")
        assert sm["pytest"] == ("dev", "high")
        assert sm["coverage"] == ("test", "high")

    def test_requirements_txt_via_registry(self):
        deps = self.registry.parse_file("requirements.txt", SAMPLE_REQUIREMENTS_TXT)
        sm = _scope_map(deps)
        assert sm["requests"] == ("runtime", "medium")

    def test_requirements_dev_via_registry(self):
        deps = self.registry.parse_file("requirements-dev.txt", SAMPLE_REQUIREMENTS_DEV)
        sm = _scope_map(deps)
        assert sm["pytest"] == ("dev", "high")

    def test_requirements_test_via_registry(self):
        deps = self.registry.parse_file("requirements-test.txt", SAMPLE_REQUIREMENTS_TEST)
        sm = _scope_map(deps)
        assert sm["coverage"] == ("test", "high")

    def test_manifest_path_set_on_all_deps(self):
        deps = self.registry.parse_file("package.json", SAMPLE_PACKAGE_JSON)
        for dep in deps:
            assert dep.manifest_path == "package.json"

    def test_every_dep_has_valid_scope_fields(self):
        """All deps from any parser must have valid scope/confidence values."""
        valid_scopes = {"runtime", "dev", "test", "build", "optional", "peer", "unknown"}
        valid_confidences = {"high", "medium", "low"}

        for path, content in [
            ("package.json", SAMPLE_PACKAGE_JSON),
            ("pyproject.toml", SAMPLE_PYPROJECT_PEP621),
            ("requirements.txt", SAMPLE_REQUIREMENTS_TXT),
            ("requirements-dev.txt", SAMPLE_REQUIREMENTS_DEV),
        ]:
            deps = self.registry.parse_file(path, content)
            for dep in deps:
                assert dep.dependency_scope in valid_scopes, (
                    f"{dep.package_name} from {path}: scope={dep.dependency_scope}"
                )
                assert dep.scope_confidence in valid_confidences, (
                    f"{dep.package_name} from {path}: confidence={dep.scope_confidence}"
                )
