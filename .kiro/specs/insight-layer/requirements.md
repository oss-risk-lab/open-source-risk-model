# Requirements Document

## Introduction

The Insight Layer is a thin, deterministic interpretation layer that converts raw supply chain graph data into human-meaningful risk signals. It composes on top of the existing maintenance risk scorer (`score_repo()`) without replacing it. The layer reads stored graph JSON from the SQLite database, extracts three direct graph signals (CVE risk, maintainer concentration, release staleness), evaluates them against bucketed thresholds, and produces a `RepoInsight` output where every score has a human-readable reason. The architecture is pure-function based with no external API calls at evaluation time. The Insight Layer reads already-computed data and never invokes scoring or ingestion logic during insight computation.

## Glossary

- **Insight_Engine**: The orchestrator module (`compute.py`) that reads a repo's graph JSON from the database, invokes signal extractors and risk rule evaluators, and assembles the final `RepoInsight` output. The Insight_Engine computes on demand and does not persist insights to a table.
- **Signal_Extractor**: A pure function in `graph_signals.py` that reads graph JSON nodes and returns a structured signal dataclass (CVESignal, MaintainerSignal, ReleaseSignal, BaseRiskSignal).
- **Risk_Rule_Evaluator**: A pure function in `risk_rules.py` that takes a structured signal dataclass and returns a `SignalEvidence` with severity, score contribution, and human-readable reason.
- **RepoInsight**: The output data model containing `base_maintenance_risk` (from existing scorer), `graph_signal_score` (from this layer), reasons, and detailed signal evidence.
- **SignalEvidence**: A frozen dataclass representing a single evaluated risk signal with `signal_name`, `severity`, `score_contribution`, `reason`, and `metadata`.
- **Graph_JSON**: The JSON-serialized supply chain graph stored in `repo_graphs.graph_json`, containing nodes of types: repo, maintainer, release, cve, registry, risk_factor.
- **CVSS_Vector**: A Common Vulnerability Scoring System vector string (e.g., `CVSS:3.1/AV:N/AC:L/...`) used to derive severity buckets for CVE nodes.
- **Contribution_Fraction**: A float (0.0–1.0) on maintainer nodes representing the proportion of commits attributed to that maintainer. This value is pre-computed during ingestion and stored on the node; the Insight Layer trusts it as-is and does not recompute contribution shares from raw commits.
- **Bot_Account**: A maintainer node whose username ends with `[bot]`, excluded from concentration analysis.
- **Graph_Signal_Score**: A float (0.0–1.0) computed by summing and capping the `score_contribution` values from all direct signal evaluations.
- **Batch_Script**: The `scripts/compute_all_insights.py` script that iterates over all repos in the database, computes insights on demand, and prints results. The Batch_Script does not persist insights to a table; persistence is deferred to a future version.
- **Insights_API_Endpoint**: The `GET /api/insights/{owner}/{repo}` FastAPI endpoint that computes insights on demand and returns a RepoInsight JSON response. The endpoint does not persist insights to a table.

## Requirements

### Requirement 1: CVE Risk Signal Extraction

**User Story:** As a risk analyst, I want CVE data extracted from graph nodes, so that the risk evaluation rules have structured CVE signal data to work with.

#### Acceptance Criteria

1. WHEN a graph JSON contains one or more nodes of type "cve", THE Signal_Extractor SHALL return a CVESignal with `total_count` equal to the number of cve nodes.
2. WHEN a cve node contains a normalized severity field (e.g., `cvss_score`), THE Signal_Extractor SHALL use that field to determine the severity bucket (critical, high, medium, low).
3. WHEN a cve node does not contain a normalized severity field but contains a `severity` metadata field with a CVSS_Vector string, THE Signal_Extractor SHALL parse the vector to determine a severity bucket (critical, high, medium, low).
4. WHEN a cve node contains neither a normalized severity field nor a parseable CVSS_Vector, THE Signal_Extractor SHALL count the cve node and include its identifier in the `cve_ids` list without assigning a severity bucket (count-only fallback with no severity bucketing).
5. WHEN a graph JSON contains zero cve nodes, THE Signal_Extractor SHALL return a CVESignal with `total_count` of 0 and empty lists.

### Requirement 2: Maintainer Concentration Signal Extraction

**User Story:** As a risk analyst, I want maintainer concentration data extracted from graph nodes, so that single-point-of-failure risks are identified.

#### Acceptance Criteria

1. WHEN a graph JSON contains maintainer nodes, THE Signal_Extractor SHALL filter out Bot_Account nodes before computing concentration metrics.
2. WHEN human maintainer nodes remain after bot filtering, THE Signal_Extractor SHALL identify the top contributor by highest `contribution_fraction` and record the username and fraction. The Signal_Extractor SHALL trust the `contribution_fraction` value already stored on the node and SHALL NOT recompute contribution shares from raw commit data.
3. WHEN a graph JSON contains zero maintainer nodes or only Bot_Account nodes, THE Signal_Extractor SHALL return a MaintainerSignal with `human_maintainer_count` of 0 and `top_contributor_fraction` of 0.0.

### Requirement 3: Release Staleness Signal Extraction

**User Story:** As a risk analyst, I want release staleness data extracted from graph nodes, so that abandoned or slow-release projects are flagged.

#### Acceptance Criteria

1. WHEN a graph JSON contains release nodes, THE Signal_Extractor SHALL locate the node where `is_latest` is true and read its `days_ago` metadata field.
2. WHEN a graph JSON contains release nodes but none has `is_latest` set to true, THE Signal_Extractor SHALL return a ReleaseSignal with `has_releases` true and `days_since_latest` as None.
3. WHEN a graph JSON contains zero release nodes, THE Signal_Extractor SHALL return a ReleaseSignal with `has_releases` false.

### Requirement 4: CVE Risk Rule Evaluation

**User Story:** As a risk analyst, I want CVE signals evaluated into severity-bucketed risk evidence, so that I get a scored and explained CVE risk assessment.

#### Acceptance Criteria

1. WHEN a CVESignal has `has_critical` true or `has_high` true, THE Risk_Rule_Evaluator SHALL return a SignalEvidence with severity "high" and a score_contribution of 0.4.
2. WHEN a CVESignal has `total_count` greater than 0 but `has_critical` and `has_high` are both false, THE Risk_Rule_Evaluator SHALL return a SignalEvidence with severity "medium" and a score_contribution of 0.2.
3. WHEN a CVESignal has `total_count` of 0, THE Risk_Rule_Evaluator SHALL return a SignalEvidence with severity "info" and a score_contribution of 0.0.
4. THE Risk_Rule_Evaluator SHALL include a human-readable reason string in every returned SignalEvidence that describes the CVE count and severity level.

### Requirement 5: Maintainer Concentration Risk Rule Evaluation

**User Story:** As a risk analyst, I want maintainer concentration evaluated against thresholds, so that bus-factor risks are scored and explained.

#### Acceptance Criteria

1. WHEN a MaintainerSignal has `top_contributor_fraction` greater than 0.8, THE Risk_Rule_Evaluator SHALL return a SignalEvidence with severity "high" and a score_contribution of 0.3.
2. WHEN a MaintainerSignal has `top_contributor_fraction` greater than 0.65 and at most 0.8, THE Risk_Rule_Evaluator SHALL return a SignalEvidence with severity "medium" and a score_contribution of 0.15.
3. WHEN a MaintainerSignal has `top_contributor_fraction` greater than 0.5 and at most 0.65, THE Risk_Rule_Evaluator SHALL return a SignalEvidence with severity "mild" and a score_contribution of 0.05.
4. WHEN a MaintainerSignal has `top_contributor_fraction` of 0.5 or less, THE Risk_Rule_Evaluator SHALL return a SignalEvidence with severity "info" and a score_contribution of 0.0.
5. THE Risk_Rule_Evaluator SHALL include the top contributor username and percentage in the reason string.

### Requirement 6: Release Staleness Risk Rule Evaluation

**User Story:** As a risk analyst, I want release staleness evaluated against time thresholds, so that stale projects are scored and explained.

#### Acceptance Criteria

1. WHEN a ReleaseSignal has `days_since_latest` greater than 365, THE Risk_Rule_Evaluator SHALL return a SignalEvidence with severity "high" and a score_contribution of 0.3.
2. WHEN a ReleaseSignal has `days_since_latest` greater than 180 and at most 365, THE Risk_Rule_Evaluator SHALL return a SignalEvidence with severity "medium" and a score_contribution of 0.15.
3. WHEN a ReleaseSignal has `days_since_latest` of 180 or less, THE Risk_Rule_Evaluator SHALL return a SignalEvidence with severity "info" and a score_contribution of 0.0.
4. WHEN a ReleaseSignal has `has_releases` false, THE Risk_Rule_Evaluator SHALL return a SignalEvidence with severity "info", a score_contribution of 0.0, and a reason noting that no release data is available.
5. WHEN a ReleaseSignal has `has_releases` true but `days_since_latest` is None, THE Risk_Rule_Evaluator SHALL return a SignalEvidence with severity "info", a score_contribution of 0.0, and a reason noting that the latest release could not be determined.
6. Absence of release metadata SHALL NOT itself contribute a positive risk score. Only explicit staleness evidence (days_since_latest exceeding a threshold) SHALL produce a non-zero score_contribution.

### Requirement 7: Insight Orchestration

**User Story:** As a risk analyst, I want a single function that computes the complete insight for a repository, so that all signals are evaluated and assembled into one output.

#### Acceptance Criteria

1. WHEN given a repo full name, THE Insight_Engine SHALL read the graph JSON from the database using the existing GraphRepository.
2. THE Insight_Engine SHALL invoke all three Signal_Extractors (CVE, maintainer, release) and the base risk extractor on the graph JSON.
3. THE Insight_Engine SHALL invoke all three Risk_Rule_Evaluators on the extracted signals.
4. THE Insight_Engine SHALL compute `graph_signal_score` by summing the `score_contribution` values from all direct signal evaluations, capped at 1.0.
5. THE Insight_Engine SHALL assign `graph_signal_label` as "HIGH" when `graph_signal_score` is 0.6 or greater, "MEDIUM" when 0.3 or greater, and "LOW" otherwise.
6. THE Insight_Engine SHALL populate the `reasons` list with the reason string from each SignalEvidence that has a severity other than "info".
7. THE Insight_Engine SHALL populate `base_maintenance_risk` and `base_maintenance_label` from the BaseRiskSignal extracted from the repo node.
8. WHEN the repo record exists in the database but has no graph JSON stored, THE Insight_Engine SHALL return a RepoInsight with default values and a reason stating "No graph data available".
9. THE Insight_Engine SHALL read the already-computed maintenance risk and label from stored graph/repo data and SHALL NOT invoke `score_repo()` or any external scoring/ingestion logic during insight computation.
10. THE Insight_Engine SHALL populate `direct_signals` in a deterministic order: cve_risk, maintainer_concentration, release_staleness.

### Requirement 8: Graph Signal Score Computation

**User Story:** As a risk analyst, I want the graph signal score to be a bounded additive composition of individual signal contributions, so that the score is predictable and explainable.

#### Acceptance Criteria

1. THE Insight_Engine SHALL compute `graph_signal_score` as the sum of all `score_contribution` values from direct signal evaluations.
2. THE Insight_Engine SHALL cap `graph_signal_score` at a maximum of 1.0.
3. Internal computation SHALL use full floating-point precision. Serialization via `to_dict()` SHALL round `graph_signal_score` and each `score_contribution` to 3 decimal places. This avoids subtle drift in round-trip tests.
4. FOR ALL valid graph inputs, computing the insight and serializing it via `to_dict()` then deserializing SHALL produce equivalent field values (round-trip property).

### Requirement 9: Insights API Endpoint

**User Story:** As a developer, I want an API endpoint that returns the computed insight for a repository, so that downstream consumers can access risk signals over HTTP.

#### Acceptance Criteria

1. WHEN a GET request is made to `/api/insights/{owner}/{repo}`, THE Insights_API_Endpoint SHALL invoke the Insight_Engine for the specified repository.
2. WHEN the Insight_Engine returns a valid RepoInsight, THE Insights_API_Endpoint SHALL return a 200 response with the RepoInsight serialized as JSON.
3. WHEN the specified repository record does not exist in the database, THE Insights_API_Endpoint SHALL return a 404 response with a descriptive error message.
4. WHEN the repository record exists in the database but has no graph JSON stored, THE Insights_API_Endpoint SHALL return a 200 response with a default RepoInsight containing a reason "No graph data available".
5. IF an unexpected error occurs during insight computation, THEN THE Insights_API_Endpoint SHALL return a 500 response with a generic error message and log the details.

### Requirement 10: Batch Insight Computation

**User Story:** As an operator, I want a batch script that computes insights for all repositories in the database, so that I can review risk signals across the full dataset.

#### Acceptance Criteria

1. WHEN executed, THE Batch_Script SHALL retrieve the list of all repositories from the database.
2. THE Batch_Script SHALL invoke the Insight_Engine for each repository and print a summary line per repo.
3. IF the Insight_Engine raises an error for a specific repository, THEN THE Batch_Script SHALL log the error and continue processing the remaining repositories.
4. WHEN all repositories have been processed, THE Batch_Script SHALL print a summary with total count, success count, and failure count.
5. THE Batch_Script SHALL compute insights on demand and print results. The Batch_Script SHALL NOT persist insights to a database table. Persistence is deferred to a future version.

### Requirement 11: RepoInsight Serialization

**User Story:** As a developer, I want RepoInsight to serialize to a stable JSON format, so that API consumers have a predictable contract.

#### Acceptance Criteria

1. THE RepoInsight `to_dict()` method SHALL include all top-level fields: `repo_full_name`, `base_maintenance_risk`, `base_maintenance_label`, `graph_signal_score`, `graph_signal_label`, `reasons`, `direct_signals`, `top_risky_dependencies`.
2. THE RepoInsight `to_dict()` method SHALL serialize each SignalEvidence in `direct_signals` with fields: `signal_name`, `severity`, `score_contribution`, `reason`.
3. THE RepoInsight `to_dict()` method SHALL round `graph_signal_score` and each `score_contribution` to 3 decimal places. Internal computation uses full precision; rounding occurs only at serialization time.
4. THE RepoInsight `to_dict()` method SHALL serialize `direct_signals` in deterministic order: cve_risk, maintainer_concentration, release_staleness.
5. In v1, `top_risky_dependencies` SHALL default to an empty list. This field will be populated when dependency-level graph risk ranking is implemented in a future version.
6. FOR ALL valid RepoInsight instances, serializing via `to_dict()` and constructing a new RepoInsight from the dict fields SHALL produce equivalent output when serialized again (round-trip property).
