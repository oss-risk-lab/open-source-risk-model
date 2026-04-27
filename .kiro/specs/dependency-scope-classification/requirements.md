# Requirements Document

## Introduction

Deep Signal currently displays undifferentiated dependency totals (e.g., NumPy showing 4410 total dependencies) without distinguishing runtime from dev/test/build/optional dependencies. This confuses users because the number conflates dependencies that matter for production risk with those that only matter during development or testing.

This feature adds **dependency scope classification** across the ingestion, storage, API, and UI layers. Each dependency relationship is tagged with a `dependency_scope` (runtime, dev, test, build, optional, peer, unknown) and a `scope_confidence` (high, medium, low) derived from ecosystem-specific manifest parsing rules. The classification is framed as a best-effort heuristic — not a guarantee of runtime truth — and is clearly labeled as "classified from manifests."

## Glossary

- **Scope_Classifier**: The module responsible for mapping parsed dependency metadata (manifest path, dependency group, ecosystem) to a `dependency_scope` and `scope_confidence` pair.
- **Dependency_Scope**: An enumeration of scope labels: `runtime`, `dev`, `test`, `build`, `optional`, `peer`, `unknown`.
- **Scope_Confidence**: An enumeration of confidence levels: `high`, `medium`, `low`.
- **Resolved_Dependencies_Table**: The `resolved_dependencies` SQLite table storing transitive dependency edges.
- **Repo_Dependencies_Table**: The `repo_dependencies` SQLite table storing direct dependency records.
- **Tree_Service**: The service that builds canonical dependency trees from the database (`src/open_source_risk_model/tree/service.py`).
- **Dependency_Parser_Registry**: The registry of manifest parsers (`src/open_source_risk_model/dependencies/parsers.py`).
- **Summary_Metrics**: The aggregate statistics object returned in dependency tree and API responses.
- **Scope_Priority**: The precedence order used when a dependency appears through multiple paths: runtime > optional > peer > build > test > dev > unknown.

## Requirements

### Requirement 1: Scope Classification Data Model

**User Story:** As a developer, I want dependency scope and confidence stored alongside each dependency record, so that downstream consumers (API, UI, tree service) can filter and summarize by scope.

#### Acceptance Criteria

1. THE Repo_Dependencies_Table SHALL include a `dependency_scope` column with allowed values: `runtime`, `dev`, `test`, `build`, `optional`, `peer`, `unknown`.
2. THE Repo_Dependencies_Table SHALL include a `scope_confidence` column with allowed values: `high`, `medium`, `low`.
3. THE Resolved_Dependencies_Table SHALL include a `dependency_scope` column with the same allowed values as the Repo_Dependencies_Table.
4. THE Resolved_Dependencies_Table SHALL include a `scope_confidence` column with the same allowed values as the Repo_Dependencies_Table.
5. WHEN existing rows lack `dependency_scope` or `scope_confidence` values, THE migration logic SHALL default those rows to `dependency_scope = 'unknown'` and `scope_confidence = 'low'`.
6. THE schema migration SHALL preserve all existing data and maintain backwards compatibility with queries that do not reference scope columns.

### Requirement 2: npm/package.json Classification Rules

**User Story:** As a developer analyzing a JavaScript project, I want npm dependencies classified by their manifest section, so that I can distinguish runtime from dev dependencies.

#### Acceptance Criteria

1. WHEN the Scope_Classifier processes a dependency from the `dependencies` section of a `package.json` file, THE Scope_Classifier SHALL assign `dependency_scope = 'runtime'` and `scope_confidence = 'high'`.
2. WHEN the Scope_Classifier processes a dependency from the `devDependencies` section of a `package.json` file, THE Scope_Classifier SHALL assign `dependency_scope = 'dev'` and `scope_confidence = 'high'`.
3. WHEN the Scope_Classifier processes a dependency from the `optionalDependencies` section of a `package.json` file, THE Scope_Classifier SHALL assign `dependency_scope = 'optional'` and `scope_confidence = 'high'`.
4. WHEN the Scope_Classifier processes a dependency from the `peerDependencies` section of a `package.json` file, THE Scope_Classifier SHALL assign `dependency_scope = 'peer'` and `scope_confidence = 'medium'`.

### Requirement 3: Python pyproject.toml Classification Rules

**User Story:** As a developer analyzing a Python project using pyproject.toml, I want dependencies classified by their declaration section, so that I can see which are runtime versus tooling.

#### Acceptance Criteria

1. WHEN the Scope_Classifier processes a dependency from the `project.dependencies` section of a `pyproject.toml` file, THE Scope_Classifier SHALL assign `dependency_scope = 'runtime'` and `scope_confidence = 'high'`.
2. WHEN the Scope_Classifier processes a dependency from the `project.optional-dependencies` section of a `pyproject.toml` file, THE Scope_Classifier SHALL assign `dependency_scope = 'optional'` and `scope_confidence = 'high'`.
3. WHEN the Scope_Classifier processes a dependency from a dependency group named `dev`, `test`, `docs`, `lint`, `typecheck`, or `tooling` in a `pyproject.toml` file, THE Scope_Classifier SHALL assign the appropriate scope (`dev`, `test`, or `build`) and `scope_confidence = 'medium'` or `'high'` based on group name specificity.
4. WHEN the Scope_Classifier processes a dependency from a `tool.*` section of a `pyproject.toml` file that is not a recognized dependency declaration, THE Scope_Classifier SHALL NOT classify that entry as a runtime dependency.

### Requirement 4: Python Requirements File Classification Rules

**User Story:** As a developer analyzing a Python project using requirements files, I want dependencies classified by filename convention, so that I can distinguish production from dev/test dependencies.

#### Acceptance Criteria

1. WHEN the Scope_Classifier processes a dependency from a file named `requirements.txt`, THE Scope_Classifier SHALL assign `dependency_scope = 'runtime'` and `scope_confidence = 'medium'`.
2. WHEN the Scope_Classifier processes a dependency from a file matching the pattern `requirements-dev.txt` or `dev-requirements.txt`, THE Scope_Classifier SHALL assign `dependency_scope = 'dev'` and `scope_confidence = 'high'`.
3. WHEN the Scope_Classifier processes a dependency from a file matching the pattern `requirements-test.txt` or `test-requirements.txt`, THE Scope_Classifier SHALL assign `dependency_scope = 'test'` and `scope_confidence = 'high'`.
4. WHEN the Scope_Classifier processes a dependency from a file matching the pattern `docs-requirements.txt` or `requirements-docs.txt`, THE Scope_Classifier SHALL assign `dependency_scope = 'build'` and `scope_confidence = 'medium'`.
5. WHEN the Scope_Classifier processes a dependency from a requirements file with an unrecognized filename pattern, THE Scope_Classifier SHALL assign `dependency_scope = 'unknown'` and `scope_confidence = 'low'`.

### Requirement 5: Poetry Classification Rules

**User Story:** As a developer analyzing a Python project using Poetry, I want dependencies classified by their Poetry group, so that I can see runtime versus dev/test/docs dependencies.

#### Acceptance Criteria

1. WHEN the Scope_Classifier processes a dependency from the main `[tool.poetry.dependencies]` section (excluding `python`), THE Scope_Classifier SHALL assign `dependency_scope = 'runtime'` and `scope_confidence = 'high'`.
2. WHEN the Scope_Classifier processes a dependency from a Poetry group named `dev`, `test`, or `docs`, THE Scope_Classifier SHALL assign the appropriate scope (`dev`, `test`, or `build`) and `scope_confidence = 'high'`.
3. WHEN the Scope_Classifier processes a dependency marked as `optional = true` in Poetry or declared under `[tool.poetry.extras]`, THE Scope_Classifier SHALL assign `dependency_scope = 'optional'` and `scope_confidence = 'high'`.

### Requirement 6: Rust Cargo.toml Classification Rules

**User Story:** As a developer analyzing a Rust project, I want Cargo.toml dependencies classified by their section, so that I can distinguish runtime from dev and build dependencies.

#### Acceptance Criteria

1. WHEN the Scope_Classifier processes a dependency from the `[dependencies]` section of a `Cargo.toml` file, THE Scope_Classifier SHALL assign `dependency_scope = 'runtime'` and `scope_confidence = 'high'`.
2. WHEN the Scope_Classifier processes a dependency from the `[dev-dependencies]` section of a `Cargo.toml` file, THE Scope_Classifier SHALL assign `dependency_scope = 'dev'` and `scope_confidence = 'high'`.
3. WHEN the Scope_Classifier processes a dependency from the `[build-dependencies]` section of a `Cargo.toml` file, THE Scope_Classifier SHALL assign `dependency_scope = 'build'` and `scope_confidence = 'high'`.

### Requirement 7: Fallback Classification

**User Story:** As a developer, I want unrecognized manifests to produce a safe default classification, so that unknown dependencies do not break scoring or display.

#### Acceptance Criteria

1. WHEN the Scope_Classifier cannot determine the scope of a dependency from its manifest metadata, THE Scope_Classifier SHALL assign `dependency_scope = 'unknown'` and `scope_confidence = 'low'`.
2. THE Scope_Classifier SHALL classify every dependency exactly once — no dependency record SHALL have a NULL `dependency_scope` after classification.

### Requirement 8: Transitive Scope Inheritance

**User Story:** As a developer, I want transitive dependencies to inherit the scope of the path that reached them, so that a dev-only transitive dependency is not counted as runtime.

#### Acceptance Criteria

1. WHEN a transitive dependency is reached through a single path, THE Scope_Classifier SHALL assign the transitive dependency the same `dependency_scope` as the direct dependency that introduced it.
2. WHEN the same transitive dependency is reached through multiple paths with different scopes, THE Scope_Classifier SHALL assign the scope with the highest Scope_Priority: runtime > optional > peer > build > test > dev > unknown.
3. THE Scope_Classifier SHALL include a code comment noting that scope is path-dependent and that the highest-risk scope is used when multiple paths exist.

### Requirement 9: Ingestion Pipeline Integration

**User Story:** As a developer, I want scope classification to happen automatically during dependency ingestion, so that every newly ingested dependency has a scope and confidence.

#### Acceptance Criteria

1. WHEN the Dependency_Parser_Registry parses a manifest file, THE parsers SHALL emit `dependency_scope` and `scope_confidence` fields on each parsed `Dependency` object.
2. WHEN the DependencyIngestionService saves dependencies to the database, THE service SHALL persist the `dependency_scope` and `scope_confidence` values from the parsed Dependency objects.
3. WHEN the transitive resolver stores edges in the Resolved_Dependencies_Table, THE resolver SHALL persist the `dependency_scope` and `scope_confidence` values on each edge.

### Requirement 10: API Response Scope Fields

**User Story:** As an API consumer, I want dependency scope information included in API responses, so that I can build scope-aware dashboards and integrations.

#### Acceptance Criteria

1. WHEN the `/api/graph` endpoint returns dependency edges, THE API SHALL include `dependency_scope` and `scope_confidence` fields on each dependency edge.
2. WHEN the dependency tree endpoint returns tree nodes, THE API SHALL include `dependency_scope` and `scope_confidence` fields on each tree node.
3. WHEN the `/api/scope/{scope_id}` endpoint returns scope data, THE API SHALL include `dependency_scope` and `scope_confidence` fields on dependency nodes.

### Requirement 11: Scope Summary Counts in API Responses

**User Story:** As an API consumer, I want summary counts broken down by scope, so that I can quickly see how many runtime versus dev dependencies a project has.

#### Acceptance Criteria

1. THE Summary_Metrics object SHALL include the following fields: `runtime_dependency_count`, `dev_dependency_count`, `test_dependency_count`, `build_dependency_count`, `optional_dependency_count`, `peer_dependency_count`, `unknown_dependency_count`, and `total_dependency_count`.
2. WHEN the Summary_Metrics are calculated, THE calculator SHALL count each dependency exactly once toward its assigned scope bucket.
3. WHERE transitive runtime dependency counts are available, THE Summary_Metrics object SHALL include a `transitive_runtime_dependency_count` field.

### Requirement 12: UI Scope Breakdown Display

**User Story:** As a user viewing dependency totals in the UI, I want to see a breakdown by scope instead of one undifferentiated number, so that I can understand how many dependencies are runtime-relevant.

#### Acceptance Criteria

1. WHEN the dependency tree UI displays summary metrics, THE UI SHALL show separate counts for: Runtime, Dev/Test, Build, Optional/Peer, Unknown, and Total.
2. THE UI SHALL replace the single "Total deps" metric card with the scope breakdown cards.
3. THE UI SHALL clearly label scope counts as "classified from manifests" to communicate that classification is heuristic-based.

### Requirement 13: UI Scope Filter Controls

**User Story:** As a user exploring the dependency tree, I want to filter by scope, so that I can focus on runtime dependencies or see all dependencies.

#### Acceptance Criteria

1. THE dependency tree UI SHALL provide a scope filter control with options: "Runtime only", "Runtime + transitive", and "All dependencies".
2. WHEN the user selects "Runtime only", THE UI SHALL display only dependencies with `dependency_scope = 'runtime'`.
3. WHEN the user selects "All dependencies", THE UI SHALL display dependencies of all scopes.
4. THE scope filter SHALL be additive with existing filters (high-risk only, vulnerable only, direct only).

### Requirement 14: Backwards Compatibility

**User Story:** As an existing user, I want the dependency tree and graph views to continue working after scope classification is added, so that no existing functionality breaks.

#### Acceptance Criteria

1. WHEN a dependency has `dependency_scope = 'unknown'`, THE Tree_Service SHALL include that dependency in all views and calculations without error.
2. THE existing dependency count fields (`total_dependencies`, `direct_dependencies`, `transitive_dependencies`) SHALL continue to be populated and accurate.
3. THE existing graph endpoint SHALL continue to return valid responses for repositories that have not been re-ingested with scope data.
4. THE existing scoring logic SHALL continue to function without requiring scope data.

### Requirement 15: Classification Unit Tests

**User Story:** As a developer, I want comprehensive unit tests for scope classification rules, so that I can verify correctness and catch regressions.

#### Acceptance Criteria

1. THE test suite SHALL include tests for npm `package.json` classification: `dependencies`, `devDependencies`, `optionalDependencies`, and `peerDependencies` sections.
2. THE test suite SHALL include tests for `pyproject.toml` classification: `project.dependencies`, `project.optional-dependencies`, and named dependency groups.
3. THE test suite SHALL include tests for Python requirements file classification: `requirements.txt`, `requirements-dev.txt`, `dev-requirements.txt`, `test-requirements.txt`, `requirements-test.txt`, and unrecognized filenames.
4. THE test suite SHALL include tests for Cargo.toml classification: `dependencies`, `dev-dependencies`, and `build-dependencies` sections.
5. THE test suite SHALL include a test confirming that an unrecognized manifest produces `dependency_scope = 'unknown'` and `scope_confidence = 'low'`.
6. THE test suite SHALL include API tests confirming that scope fields appear in dependency tree and graph responses.
7. THE test suite SHALL include regression tests confirming that existing dependency counts remain accurate after scope classification is added.

### Requirement 16: Scope Classifier Round-Trip Property

**User Story:** As a developer, I want to verify that scope classification is deterministic and consistent, so that the same input always produces the same scope output.

#### Acceptance Criteria

1. FOR ALL valid manifest metadata inputs, classifying the same input twice SHALL produce identical `dependency_scope` and `scope_confidence` values (idempotence property).
2. FOR ALL classified dependencies, the `dependency_scope` value SHALL be one of the seven defined scope values and the `scope_confidence` value SHALL be one of the three defined confidence values (output domain property).
