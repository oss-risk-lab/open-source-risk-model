# Implementation Plan: Pre-Deployment Finalization

## Overview

Prepare Deep Signal for production deployment and demo readiness by creating a curated demo repo config with validation, adding stats and demo-repos API endpoints, wiring the homepage to live data, building retry and QA scripts, and updating deployment configuration. Implementation follows the strict order: config → stats → demo-repos → homepage → retry → QA → deployment.

## Tasks

- [x] 1. Demo Repo Config and Loader
  - [x] 1.1 Create `src/open_source_risk_model/config/demo_repos.yaml` with 19 candidate repos
    - Define YAML structure with `repos` list, each entry having `repo` (owner/repo) and `tags` fields
    - Include all 19 candidate repos from design: numpy/numpy, pallets/flask, django/django, facebook/react, expressjs/express, axios/axios, psf/requests, scikit-learn/scikit-learn, tensorflow/tensorflow, lodash/lodash, minimistjs/minimist, Marak/colors.js, dominictarr/event-stream, AhmedAli7O1/node-ipc, fastapi/fastapi, torvalds/linux, vuejs/vue, yaml/pyyaml, ytdl-org/youtube-dl
    - Tags from allowed set: `high-risk`, `deep-tree`, `well-maintained`, `popular`, `vulnerable`
    - Note: these are initial candidates; the final demo set is determined by `validate_demo_repos()` which filters out repos that fail DB validation
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 1.2 Create `src/open_source_risk_model/config/demo_repos.py` loader module
    - Implement `DemoRepo` and `DemoRepoConfig` dataclasses
    - Implement `load_demo_repos()` to parse YAML from the config directory
    - Implement `validate_demo_repos(db_path)` that checks each repo against `repo_graphs`, `repo_dependencies`, and `compute_repo_insight` returning non-null score
    - Log warnings for repos failing validation with repo name and missing data category
    - Return only repos passing all three checks
    - _Requirements: 2.4, 2.5, 2.6, 2.7_

  - [x] 1.3 Write property test for demo repo validation (Property 1)
    - **Property 1: Demo Repo Validation Correctness**
    - Create `test/deployment/test_demo_repo_validation_properties.py`
    - Generate random repo configs (1–30 entries) and random DB states (subsets in repo_graphs, repo_dependencies)
    - Mock `compute_repo_insight` to return null or non-null randomly
    - Verify validated list matches expected intersection of all three conditions
    - Verify warnings logged for each failing repo with correct missing category
    - **Validates: Requirements 2.4, 2.5, 2.6, 2.7**

  - [x] 1.4 Write unit tests for demo repo config loading
    - Test valid YAML loading, missing file raises FileNotFoundError, invalid YAML raises ValueError
    - Test entries with valid/invalid tags, missing repo field
    - _Requirements: 2.1, 2.2, 2.3_

- [x] 2. Stats Endpoint
  - [x] 2.1 Add `GET /api/stats` endpoint to `api/app.py`
    - Query `repo_graphs` for `total_repos`: `SELECT COUNT(DISTINCT repo_full_name) FROM repo_graphs`
    - Query intersection of `repo_graphs` AND `repo_dependencies` for `fully_analyzed_repos`: `SELECT COUNT(DISTINCT rg.repo_full_name) FROM repo_graphs rg INNER JOIN repo_dependencies rd ON rg.repo_full_name = rd.repo_full_name`
    - Compute `coverage_ratio = round(fully_analyzed / total, 2)`, return 0.00 when total is 0
    - Return HTTP 503 if database is unavailable
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [x] 2.2 Write property test for stats computation (Property 2)
    - **Property 2: Stats Computation Correctness**
    - Create `test/deployment/test_stats_computation_properties.py`
    - Generate random sets of repo names for repo_graphs (0–50) and repo_dependencies (0–50)
    - Insert into in-memory SQLite, call stats computation, verify all three fields
    - Verify `fully_analyzed_repos` counts only repos present in BOTH tables
    - **Validates: Requirements 4.2, 4.3, 4.4, 4.5**

  - [x] 2.3 Write unit tests for stats endpoint
    - Test empty DB returns zeros, single repo, mixed state (repo in graphs but not deps), DB unavailable returns 503
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 3. Checkpoint — Run all tests, verify no regressions
  - Run full test suite. Continue if all pass. Stop only for true blocking failures.

- [x] 4. Demo Repos Endpoint
  - [x] 4.1 Add `GET /api/demo-repos` endpoint to `api/app.py`
    - Load repos from `demo_repos.yaml` via `load_demo_repos()`
    - Run `validate_demo_repos(db_path)` to filter to only validated repos before enrichment
    - Enrich each validated entry with `risk_label` from `compute_repo_insight` (set null on failure)
    - Return JSON with `repos` array containing `repo`, `name`, `owner`, `tags`, `risk_label`
    - If DB unavailable, return repos from YAML without enrichment (`risk_label: null` for all)
    - Invalid repos are excluded from the response — only validated repos are returned
    - _Requirements: 3.1, 3.2_

  - [x] 4.2 Write unit tests for demo-repos endpoint
    - Test returns enriched list with only validated repos
    - Test handles missing insights gracefully (risk_label null)
    - Test DB unavailable fallback returns unenriched list
    - _Requirements: 3.1, 3.2_

- [x] 5. Homepage Wiring
  - [x] 5.1 Create `ui/config.js` with configurable API_BASE
    - Set `window.DS_API_BASE = window.DS_API_BASE || ""`
    - _Requirements: 6.3_

  - [x] 5.2 Update `ui/index.html` to fetch from API endpoints
    - Import `config.js` script
    - Remove hardcoded `EXPLORE` object entirely
    - On load, fetch `DS_API_BASE + "/api/demo-repos"` and `DS_API_BASE + "/api/stats"`
    - Group repo chips by tags: "Higher Risk" (repos tagged `high-risk`), "Well Maintained" (repos tagged `well-maintained`), "Popular" (repos tagged `popular` that are not already in the above groups)
    - Each chip shows repo name, owner, and a risk-level indicator dot derived from `risk_label` (HIGH → red, MEDIUM → yellow, LOW → green, null → neutral)
    - The `risk_label` is used only for the indicator dot color, not for grouping
    - Clicking a chip navigates to `insights.html?repo=owner/repo`
    - Add trust signal line: "Analyzing {N}+ open-source repositories..." using `total_repos` from stats
    - Fallback: if stats fails, show "100+" as the count
    - Fallback: if demo-repos fails, show "Unable to load repositories" message in the explore section
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.6_

  - [x] 5.3 Update `ui/graph.html`, `ui/insights.html`, `ui/dependency-tree.html` to use `config.js`
    - Add `<script src="config.js"></script>` before existing scripts
    - Replace hardcoded `API_BASE` / `INSIGHT_API_BASE` variables with `window.DS_API_BASE`
    - _Requirements: 6.3_

- [x] 6. Checkpoint — Run all tests, verify no regressions
  - Run full test suite including UI tests. Continue if all pass. Stop only for true blocking failures.

- [x] 7. Retry Rate-Limited Script
  - [x] 7.1 Create `scripts/retry_rate_limited.py`
    - Target repos: `["yaml/pyyaml", "ytdl-org/youtube-dl"]`
    - For each repo, execute the full pipeline in order:
      1. `DependencyIngestionService.ingest_repo(repo, refresh=True, resolve_packages=True)` — parse direct dependencies
      2. `TransitiveResolver.resolve_repo()` — resolve transitive dependencies
      3. `ResolvedDependencyStorage.store_edges()` — persist resolved edges
      4. Run graph enrichment (call `enrich_graphs` logic or equivalent) — enrich the repo graph with dependency data
      5. `compute_repo_insight()` — compute insight scores
    - After pipeline completes for each repo, validate:
      - Dependency count > 0 (check `repo_dependencies` table)
      - Graph edges > 0 (check `repo_graphs` data)
      - Insight score is non-null (check `compute_repo_insight` return)
    - Log HTTP status codes on rate-limit failures (403)
    - Log success with repo name, dependency count, edge count, and insight score
    - Log failure with repo name and specific error
    - Exit 0 if both repos pass all validation checks, exit 1 if any repo fails
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [x] 7.2 Write unit tests for retry script
    - Mock successful ingestion with validation checks passing
    - Mock rate-limit failure with correct logging and exit code 1
    - Mock partial failure (ingestion succeeds but validation fails) with correct exit code 1
    - _Requirements: 1.1, 1.6_

- [ ] 8. QA Validation Script
  - [x] 8.1 Create `scripts/validate_demo_repos.py`
    - Accept `--api-base` argument (default `http://127.0.0.1:8000`)
    - Load demo repos from config via `validate_demo_repos()` (use only validated repos)
    - Test at least 5 repos
    - For each repo test: `/api/insights/{owner}/{repo}` (200, non-null score), `/api/graph?repo={owner}/{repo}` (200, ≥1 node, ≥1 edge), `/repos/{owner}/{repo}/dependency-tree` (200, non-empty tree), `/api/score?repo={owner}/{repo}` (200)
    - Also test: `/api/stats` (200, valid fields with total_repos > 0), `/api/demo-repos` (200, non-empty list)
    - On failure: report repo name, endpoint path, HTTP status code, response body summary
    - Print summary: `PASSED: X | FAILED: Y | TOTAL: Z`
    - Return exit code 0 if all pass, 1 if any fail
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [x] 8.2 Write property test for QA report consistency (Property 3)
    - **Property 3: QA Report Consistency**
    - Create `test/deployment/test_qa_report_properties.py`
    - Generate random lists of test results (pass/fail with repo name, endpoint, status code, body)
    - Feed to report generator, verify `passed + failed == total`
    - Verify every failed test includes repo name, endpoint path, HTTP status code, and response body summary
    - **Validates: Requirements 5.6, 5.7**

- [x] 9. Deployment Configuration Updates
  - [x] 9.1 Update CORS and startup validation in `api/app.py`
    - Read `CORS_ALLOWED_ORIGINS` from env var, fall back to `["*"]` for dev
    - Add startup check: log warning if `GITHUB_TOKEN` is not set
    - Ensure backend continues in degraded mode without token
    - _Requirements: 6.1, 6.2, 6.3, 6.7_

  - [x] 9.2 Update `docs/DEPLOYMENT.md` with pre-deployment configuration
    - Document required env vars: `GITHUB_TOKEN`, `OPENAI_API_KEY`, `GRAPH_DB_PATH`, `GRAPH_DB_ENABLED`
    - Document optional env vars: `CORS_ALLOWED_ORIGINS`, `DS_API_BASE`
    - Add frontend `API_BASE` configuration strategy via `config.js`
    - Add CORS configuration for production
    - Document steps to deploy backend and serve static frontend
    - _Requirements: 6.1, 6.3, 6.4, 6.5, 6.6_

- [x] 10. Final Checkpoint — Run full test suite and QA script
  - Run all unit and property tests. Run QA validation script against running server. Continue only if all pass. Stop for any blocking failure.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints verify incremental correctness — execution continues automatically unless a true blocking failure occurs
- Property tests validate universal correctness properties from the design document
- The YAML config contains candidate repos; the validated subset (via `validate_demo_repos`) is what gets served to users
- Homepage groups repos by tags (high-risk, well-maintained, popular); `risk_label` is used only for the indicator dot color
- `fully_analyzed_repos` in the stats endpoint counts repos present in BOTH `repo_graphs` AND `repo_dependencies`
- The retry script includes graph enrichment as an explicit pipeline step and validates dependency count, graph edges, and insight score after completion
- No new database tables are created; all queries use existing `repo_graphs`, `repo_dependencies`, and `resolved_dependencies` tables
