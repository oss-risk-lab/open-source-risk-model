# Task 22: Benchmark Parity Validation Framework

**Date**: 2025-01-24
**Status**: 🟡 FRAMEWORK COMPLETE | ⏸️ EXECUTION DEFERRED

## Overview

Benchmark parity validation ensures the new system produces the same maintenance risk scores as the current system. This is critical for trust and adoption.

## Framework Components

### 1. Benchmark Repository Selection

**Criteria**:
- 10-20 representative repos already in database
- Variety: active/inactive, large/small, different ecosystems
- Include edge cases: archived repos, stale repos, active repos

**Suggested Repos**:
```
# Active, well-maintained
- django/django
- pallets/flask
- numpy/numpy
- pandas-dev/pandas

# Less active
- tornadoweb/tornado
- bottlepy/bottle

# Different ecosystems
- facebook/react (npm)
- vuejs/vue (npm)
- spring-projects/spring-boot (maven)

# Edge cases
- archived repos
- repos with few contributors
- repos with many issues
```

### 2. Baseline Capture

**Script**: `scripts/capture_baseline_scores.py`

```python
"""
Capture baseline scores from current system.

Usage:
    python scripts/capture_baseline_scores.py \\
        --repos repos.txt \\
        --output baseline_scores.json
"""

import json
from pathlib import Path
from open_source_risk_model.persistence.db import get_connection

def capture_baseline(repo_list: list[str], db_path: str) -> dict:
    """Capture current scores from database."""
    conn = get_connection(db_path)
    baseline = {}
    
    for repo in repo_list:
        cursor = conn.execute("""
            SELECT 
                repo_full_name,
                maintenance_risk_score,
                features_json
            FROM ingestion_results
            WHERE repo_full_name = ?
        """, (repo,))
        
        row = cursor.fetchone()
        if row:
            baseline[repo] = {
                "score": row[1],
                "features": json.loads(row[2])
            }
    
    conn.close()
    return baseline
```

### 3. New System Execution

**Script**: `scripts/run_new_system_benchmark.py`

```python
"""
Run new system on benchmark repos.

Usage:
    python scripts/run_new_system_benchmark.py \\
        --repos repos.txt \\
        --output new_scores.json
"""

from open_source_risk_model.query.live_repo_ingestor import LiveRepoIngestor

def run_new_system(repo_list: list[str], github_token: str) -> dict:
    """Run new system on repos."""
    ingestor = LiveRepoIngestor(github_token=github_token)
    
    results = {}
    for repo in repo_list:
        summaries = ingestor.ingest(
            repo_identifiers=[repo],
            mode="full",
            persistence_mode="temporary"
        )
        
        if summaries:
            summary = summaries[0]
            results[repo] = {
                "score": summary.maintenance_risk_score,
                "features": summary.features
            }
    
    return results
```

### 4. Comparison and Validation

**Script**: `scripts/compare_scores.py`

```python
"""
Compare baseline vs new system scores.

Usage:
    python scripts/compare_scores.py \\
        --baseline baseline_scores.json \\
        --new new_scores.json \\
        --output comparison_report.json
"""

def compare_scores(baseline: dict, new: dict, 
                   score_tolerance: float = 0.01,
                   feature_tolerance: float = 0.05) -> dict:
    """Compare scores and generate report."""
    report = {
        "total_repos": len(baseline),
        "passing": 0,
        "failing": 0,
        "details": []
    }
    
    for repo, baseline_data in baseline.items():
        if repo not in new:
            report["details"].append({
                "repo": repo,
                "status": "missing",
                "reason": "Not in new system results"
            })
            report["failing"] += 1
            continue
        
        new_data = new[repo]
        
        # Compare scores
        score_diff = abs(baseline_data["score"] - new_data["score"])
        score_pass = score_diff <= score_tolerance
        
        # Compare features
        feature_diffs = {}
        for feature, baseline_value in baseline_data["features"].items():
            if feature in new_data["features"]:
                new_value = new_data["features"][feature]
                if baseline_value != 0:
                    pct_diff = abs((new_value - baseline_value) / baseline_value)
                    feature_diffs[feature] = {
                        "baseline": baseline_value,
                        "new": new_value,
                        "pct_diff": pct_diff,
                        "pass": pct_diff <= feature_tolerance
                    }
        
        all_features_pass = all(f["pass"] for f in feature_diffs.values())
        
        if score_pass and all_features_pass:
            report["passing"] += 1
            status = "pass"
        else:
            report["failing"] += 1
            status = "fail"
        
        report["details"].append({
            "repo": repo,
            "status": status,
            "score_diff": score_diff,
            "score_pass": score_pass,
            "feature_diffs": feature_diffs,
            "all_features_pass": all_features_pass
        })
    
    report["pass_rate"] = report["passing"] / report["total_repos"]
    
    return report
```

### 5. Report Generation

**Output Format**:
```json
{
  "version": "1.0",
  "generated_at": "2025-01-24T...",
  "total_repos": 15,
  "passing": 14,
  "failing": 1,
  "pass_rate": 0.933,
  "score_tolerance": 0.01,
  "feature_tolerance": 0.05,
  "details": [
    {
      "repo": "django/django",
      "status": "pass",
      "score_diff": 0.003,
      "score_pass": true,
      "feature_diffs": {
        "days_since_last_push": {
          "baseline": 5.2,
          "new": 5.3,
          "pct_diff": 0.019,
          "pass": true
        }
      },
      "all_features_pass": true
    }
  ],
  "summary": {
    "acceptable_differences": [
      "Snapshot timing differences (< 1 day)",
      "Release detection variations"
    ],
    "concerning_differences": []
  }
}
```

## Execution Steps

### Step 1: Select Benchmark Repos
```bash
# Create benchmark repo list
cat > benchmark_repos.txt << EOF
django/django
pallets/flask
numpy/numpy
pandas-dev/pandas
tornadoweb/tornado
EOF
```

### Step 2: Capture Baseline
```bash
python scripts/capture_baseline_scores.py \\
    --repos benchmark_repos.txt \\
    --output data/baseline_scores.json
```

### Step 3: Run New System
```bash
python scripts/run_new_system_benchmark.py \\
    --repos benchmark_repos.txt \\
    --output data/new_scores.json
```

### Step 4: Compare and Validate
```bash
python scripts/compare_scores.py \\
    --baseline data/baseline_scores.json \\
    --new data/new_scores.json \\
    --output data/parity_report.json
```

### Step 5: Review Report
```bash
cat data/parity_report.json | jq '.summary'
```

## Acceptance Criteria

✅ Pass Rate >= 90%
✅ Score differences <= ±0.01
✅ Feature differences <= ±5%
✅ No concerning divergences
✅ Acceptable differences documented

## Expected Differences

**Acceptable**:
- Snapshot timing (< 1 day difference)
- Release detection (minor variations)
- Contributor counts (recent activity)

**Concerning**:
- Score differences > 0.05
- Feature differences > 10%
- Systematic bias in one direction

## Why Deferred

Benchmark parity validation requires:
1. Access to production database with existing scores
2. Valid GitHub API token for live ingestion
3. Time to run full ingestion on 10-20 repos (~2-3 hours)
4. Analysis of results and investigation of differences

This is best done as a separate validation phase after deployment.

## Recommendation

Execute benchmark parity validation as part of:
1. Pre-production validation
2. Staged rollout testing
3. A/B testing in production

## Framework Status

✅ Selection criteria defined
✅ Scripts outlined
✅ Comparison logic specified
✅ Report format defined
✅ Execution steps documented
✅ Acceptance criteria established

## Conclusion

The framework for benchmark parity validation is complete and ready for execution. The actual validation should be performed when:
1. Production database is available
2. GitHub API access is configured
3. Sufficient time is allocated for full execution and analysis

This is a critical validation step but can be deferred to pre-production testing phase.
