# Data Directory Guide

This document explains the structure and purpose of files in the `data/` directory.

## Directory Structure

```
data/
├── baseline/              # Population distributions for risk normalization
├── issues/               # Cached issue data by repository
├── universe/             # Repository universe files for snapshot collection
└── raw_snapshots/        # Cached repository metadata snapshots
```

---

## Baseline Populations

**Location:** `data/baseline/`

These files contain population distributions used for percentile-based risk mapping (Option B).

### Files

- `days_since_last_push_population.json` - Active repositories (high stars, recent pushes)
- `days_since_last_push_population_broad.json` - Typical OSS repositories (broad mix)
- `days_since_last_push_population_combined.json` - Combined population (active + typical + stale)

### Format

```json
[0.5, 1.2, 3.4, 5.6, ...]
```

Each file contains a list of numeric values representing the distribution of a feature across sampled repositories.

### Purpose

Population files enable percentile-based risk scoring. For example, if a repository has 30 days since last push, and 80% of the population has fewer days, the risk score would be 0.8.

### Regenerating Baselines

To refresh population data:

```bash
python test/build_days_since_last_push_population.py
python test/save_days_since_population_combined.py
```

**Note:** Requires a GitHub token with sufficient rate limit quota.

---

## Issue Data

**Location:** `data/issues/{owner}__{repo}/`

Cached issue data for repositories that have been scored with `fetch_issues=true`.

### Files per Repository

- `manifest.json` - Metadata about the cached data
- `issues.jsonl` - Issue records (one JSON object per line)
- `comments.jsonl` - Comment records (one JSON object per line)

### Manifest Format

```json
{
  "full_name": "numpy/numpy",
  "last_updated": "2026-02-13T10:30:00Z",
  "issue_count": 1234,
  "comment_count": 5678
}
```

### Issue Record Format (JSONL)

```json
{
  "number": 12345,
  "title": "Bug in array indexing",
  "state": "open",
  "created_at": "2025-01-15T10:00:00Z",
  "closed_at": null,
  "user": "username",
  "labels": ["bug", "priority-high"]
}
```

### Purpose

Caching issue data:
1. Reduces GitHub API calls
2. Enables faster re-scoring
3. Supports offline analysis

### Refreshing Issue Data

Use the API with `refresh=true`:

```bash
curl "http://localhost:8000/api/score?repo=numpy/numpy&refresh=true"
```

Or delete the repository directory to force a fresh fetch.

---

## Raw Snapshots

**Location:** `data/raw_snapshots/{owner}__{repo}.json`

Cached repository metadata from the GitHub API.

### Format

```json
{
  "full_name": "numpy/numpy",
  "stargazers_count": 28500,
  "open_issues_count": 2100,
  "archived": false,
  "pushed_at": "2026-02-12T15:30:00Z",
  "license": {
    "key": "bsd-3-clause",
    "name": "BSD 3-Clause"
  },
  "__meta__": {
    "fetched_at": "2026-02-13T10:30:00Z",
    "source": "github_api"
  }
}
```

### Purpose

Snapshots enable:
1. Offline scoring and analysis
2. Historical comparisons
3. Reduced API usage
4. Reproducible evaluations

### Snapshot Lifecycle

- Created on first score request
- Updated when `refresh=true` is used
- Retained indefinitely (not auto-expired)

---

## Data Management

### Disk Space

Issue data can grow large for active repositories:
- Small repo: ~1-5 MB
- Large repo: ~50-200 MB

### Cleanup

Remove cached data for a specific repository:

```bash
rm -rf data/issues/numpy__numpy
rm data/raw_snapshots/numpy__numpy.json
```

Remove all cached data:

```bash
rm -rf data/issues/*
rm data/raw_snapshots/*
```

**Note:** Baseline populations should not be deleted unless regenerating.

---

## Version Control

### What's Committed

- ✅ Baseline population files (reproducibility)
- ✅ Gold standard snapshots (evaluation)
- ❌ User-generated issue caches (too large)
- ❌ User-generated snapshots (too large)

### .gitignore

The following patterns exclude user-generated data:

```
data/issues/*/
data/raw_snapshots/*.json
!data/raw_snapshots/numpy__numpy.json  # Example: keep gold standard
```

---

## Best Practices

1. **Use cached data** - Set `refresh=false` unless you need current data
2. **Periodic cleanup** - Remove old snapshots to save disk space
3. **Backup baselines** - Keep baseline populations in version control
4. **Document changes** - Note when baselines are regenerated

---

## Longitudinal Snapshots

The temporal snapshot engine collects a weekly, immutable observation of every repository in the universe. These records are the foundation for survival analysis and package abandonment modeling.

See [docs/data/SNAPSHOTS.md](data/SNAPSHOTS.md) for:

- Full v1.0 schema reference (record fields, features, raw fields, manifest fields)
- Observatory directory layout
- pandas load example
- Append-only and death-signal policies
- How to run locally and trigger a manual workflow
