# Longitudinal Snapshot Data

Deep Signal collects weekly, immutable observations of every repository in the universe. These snapshots are the raw material for survival analysis, trend detection, and abandonment modeling.

---

## Observatory Layout

Snapshot data lives in a dedicated repository (`deep-signal-observatory`) that is never committed to this repo. The layout is:

```
observatory/
├── snapshots/
│   └── <year>/
│       └── deep-signal-snapshot-<YYYY-MM-DD>.jsonl.gz
└── manifests/
    └── <YYYY-MM-DD>.json
```

Each `deep-signal-snapshot-<date>.jsonl.gz` contains one JSON line per repository. Each `<date>.json` manifest summarises the run that produced it.

---

## Schema v1.0: Snapshot Record

Each line in a `.jsonl.gz` file is a JSON object with the following fields:

| Field | Type | Description |
|---|---|---|
| `schema_version` | string | Always `"1.0"` |
| `run_id` | string | `snap-YYYYMMDD-HHMMSS` or `epoch0-YYYY-MM-DD` for backfill |
| `observed_at` | string | UTC ISO 8601 timestamp of when this repo was fetched |
| `repo_full_name` | string | `owner/repo` (GitHub format) |
| `universe_version` | string | Universe file that defined the population (e.g. `"v1"`) |
| `fetch_status` | string | See fetch_status values below |
| `error_message` | string or null | Present when `fetch_status` is not `success` |
| `features` | object | 14 canonical feature keys; null for any that could not be computed |
| `raw` | object | Absolute timestamps and repo metadata from the API |
| `feature_coverage` | number | Fraction of non-null values across all 14 feature keys (0.0 to 1.0). See modeling note below. |
| `feature_status` | object | Per-feature pipeline status flags from the ingestion pipeline |

### fetch_status values

| Value | Meaning |
|---|---|
| `success` | All data fetched; applicable feature coverage >= 60% |
| `partial` | Data fetched but applicable feature coverage < 60% |
| `not_found` | HTTP 404 or 451; repo was deleted, made private, or legally removed. This is a **death event** for survival analysis -- it must never be filtered out. |
| `error` | Transient failure (rate limit, timeout, 5xx). Not a death event. |

**Modeling note -- `partial` is confounded with repo size.** The `fetch_status` classifier uses `check_feature_coverage()`, which excludes inapplicable features from the denominator (for example, all 7 issue-related features are `not_applicable` when a repo has issues disabled). A healthy repo with `has_issues=False` can therefore be classified `success` while its stored `feature_coverage` field reads 0.50 (7 applicable features out of 14 total keys). Do not use `fetch_status=partial` as a model covariate without first checking `feature_status` to distinguish genuinely missing data from features that were not applicable. For Phase 2 survival modeling, use `feature_status` values directly rather than the aggregate `feature_coverage` scalar.

### features object: v1.0 canonical keys

All 14 keys are always present; missing values are `null` rather than omitted.

| Key | Type | Description |
|---|---|---|
| `days_since_last_push` | number or null | Days between observed_at and last git push |
| `days_since_last_release` | number or null | Days between observed_at and latest GitHub release |
| `stars_count` | integer or null | GitHub star count at observation time |
| `archived` | boolean or null | True if GitHub marks the repo archived |
| `open_issues_count` | integer or null | Open issue count at observation time |
| `contributors_count` | integer or null | Distinct contributors in the repo's full history |
| `contributors_last_12mo` | integer or null | Distinct contributors in the 12 months before observed_at |
| `top_contributor_fraction_12mo` | number or null | Fraction of commits by the top contributor in last 12 months |
| `issues_per_contributor` | number or null | open_issues_count / contributors_count |
| `fraction_issues_closed_12mo` | number or null | Fraction of issues opened in last 12 months that were closed |
| `fraction_open_issues_stale_180d` | number or null | Fraction of currently open issues with no activity in 180 days |
| `avg_time_to_first_maintainer_response_days` | number or null | Mean days until a maintainer first comments on a new issue |
| `median_time_to_close_days` | number or null | Median days from open to close for issues closed in last 12 months |
| `open_issue_age_p90_days` | number or null | 90th-percentile age of currently open issues in days |

### raw object

Absolute timestamps and fields sourced directly from the GitHub API, stored without transformation.

| Key | Type | Description |
|---|---|---|
| `pushed_at` | string or null | ISO 8601 timestamp of last push |
| `created_at` | string or null | ISO 8601 repository creation timestamp (null in v1 -- requires separate call) |
| `archived` | boolean or null | Repo archived flag |
| `disabled` | boolean or null | Repo disabled flag (null in v1) |
| `fork` | boolean or null | Whether the repo is a fork (null in v1) |
| `license_spdx_id` | string or null | SPDX license identifier |
| `default_branch` | string or null | Default branch name (null in v1) |
| `latest_release_tag` | string or null | Tag of the latest GitHub release (null in v1) |
| `latest_release_published_at` | string or null | ISO 8601 published timestamp of latest release |

---

## Schema v1.0: Manifest

Each `<date>.json` file records the outcome of the run that produced the corresponding snapshot.

| Field | Type | Description |
|---|---|---|
| `schema_version` | string | Always `"1.0"` |
| `run_id` | string | Matches the `run_id` in every record in the corresponding snapshot |
| `started_at` | string | UTC ISO 8601 run start time |
| `completed_at` | string | UTC ISO 8601 run end time |
| `universe_version` | string | Universe file label |
| `universe_sha256` | string | SHA-256 hex digest of the universe file at run time |
| `repos_total` | integer | Total repos in the universe slice |
| `repos_success` | integer | Count with `fetch_status=success` |
| `repos_partial` | integer | Count with `fetch_status=partial` |
| `repos_not_found` | integer | Count with `fetch_status=not_found` (death events) |
| `repos_error` | integer | Count with `fetch_status=error` (transient failures) |
| `error_sample` | array | Up to 20 `{repo, message}` objects from failed repos |
| `api_calls_estimate` | integer | Estimated GitHub API calls made during the run |
| `collector_git_sha` | string | Short git SHA of the collector at run time |
| `epoch0` | boolean | Present and `true` only on backfill manifests |

---

## Loading Snapshots with pandas

```python
import pandas as pd

df = pd.read_json(
    "observatory/snapshots/2026/deep-signal-snapshot-2026-07-13.jsonl.gz",
    lines=True,
    compression="gzip",
)
features = pd.json_normalize(df["features"])
```

---

## Append-Only Policy

Snapshot files are **never modified or deleted** after creation. Each run produces exactly one new file. If a run must be retried for the same date, use `--force` on the CLI; this replaces the file atomically. Once data is pushed to the observatory repository, it is permanent.

Do not add UPDATE or DELETE logic to any snapshot code path. If you find yourself writing one, stop and reconsider.

---

## Death-Signal Semantics

The following are all health signals and must be **recorded, never filtered**:

- `features.archived = true` -- maintainers have explicitly archived the repo.
- `raw.disabled = true` -- GitHub has disabled the repo.
- `fetch_status = not_found` -- the repo returned HTTP 404 or 451, meaning it was deleted, made private, or removed under a legal order.

A `not_found` record is the primary death event for package abandonment modeling. Silently dropping these observations corrupts survival curves.

---

## Running Locally

Fetch 10 repos as a smoke test (no data is pushed to the observatory):

```bash
GITHUB_TOKEN=<your-pat> python -m open_source_risk_model.cli.snapshot \
  --universe data/universe/universe_v1.txt \
  --output-dir /tmp/obs \
  --max-repos 10
```

Validate the output:

```bash
python scripts/validate_snapshot_run.py \
  --snapshot-file /tmp/obs/snapshots/$(date +%Y)/deep-signal-snapshot-$(date +%F).jsonl.gz \
  --manifest-file /tmp/obs/manifests/$(date +%F).json
```

---

## Triggering a Manual Workflow Run

Navigate to **Actions > weekly-snapshot > Run workflow** in the GitHub UI. The `max_repos` input limits the run to the first N repos in the universe, which is useful for smoke-testing a new universe file before the next scheduled Sunday run. Leave `max_repos` blank for a full production run.

---

## Phase 2 Modeling Notes

These notes document invariants and known asymmetries in the data that Phase 2 analysis must account for.

### Survival model setup

- **Death event**: the first `fetch_status = not_found` observation for a repo.
- **Censored observations**: any record with `fetch_status = error`. Treat as missing data, not death. A rate-limit failure or transient timeout tells you nothing about whether the repo still exists.
- **Entry time**: the `observed_at` timestamp of a repo's first record in the panel. Repos added to the universe later (e.g., a future Stratum D expansion) will have fewer observations than epoch0 repos -- survival models handle this as left truncation, not bias.

### feature_coverage vs. feature_status

The stored `feature_coverage` scalar is the fraction of all 14 feature keys that are non-null. It uses 14 as the denominator unconditionally. The classifier uses `check_feature_coverage()`, which excludes inapplicable features before computing the fraction. These two values differ for repos where some features are structurally unavailable:

- Repos with `has_issues=False` (issues disabled): all 7 issue-related features are null in the record; `feature_coverage` = 0.50. The classifier treats them as `success` because applicable coverage is 7/7.
- Repos with no releases: `days_since_last_release` is null; `feature_coverage` is reduced by 1/14.

**Do not use `feature_coverage` as a covariate directly.** Use the individual feature values, treating null as missing, and check `feature_status` to distinguish `"not_applicable"` (structurally unavailable) from `"missing"` (failed to fetch) before imputing.

### partial is not a reliable alive indicator by itself

`fetch_status = partial` means the repo is accessible but some features could not be fetched. It is systematically correlated with small repos (few or no issues, no releases, single maintainer), which are also the population most likely to die. Using `partial` as a raw covariate will conflate data-availability effects with genuine risk signals.
