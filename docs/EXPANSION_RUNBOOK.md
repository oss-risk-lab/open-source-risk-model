# Dataset Expansion Runbook

This runbook provides step-by-step instructions for expanding the open source risk model dataset from 51 to 200 repositories.

## Overview

The expansion process consists of 6 phases:
1. **Repository Selection** - Select 149 additional repositories
2. **Pre-Expansion Backup** - Create database backup
3. **Batch Ingestion** - Ingest selected repositories
4. **Validation** - Verify data quality and performance
5. **Signal Quality Analysis** - Identify cross-repository insights
6. **Reporting** - Generate expansion summary report

## Prerequisites

- GitHub personal access token with repo access
- Sufficient disk space (~500MB for backup)
- 24 hours for full ingestion
- Python 3.11+ with all dependencies installed

## Phase 1: Repository Selection

### Dry Run (Recommended First Step)

Generate repository selection without ingesting:

```bash
export GITHUB_TOKEN="your_github_token"
python scripts/expand_dataset.py expand --dry-run
```

This will:
- Calculate number of repos to add (200 - current count)
- Query GitHub API for candidates
- Apply selection criteria (>1000 stars, recent commits, ecosystem diversity)
- Save selection to `data/expansion_reports/selection_TIMESTAMP.json`

### Review Selection

Review the generated selection file:

```bash
cat data/expansion_reports/selection_*.json | jq '.repositories[] | {name: .full_name, stars, ecosystem: .primary_ecosystem}'
```

Verify:
- Total count matches expected (149 repos)
- Ecosystem distribution meets targets:
  - npm: 38-60 repos (25-40%)
  - pypi: 38-60 repos (25-40%)
  - go: ≥15 repos (≥10%)
  - maven: ≥15 repos (≥10%)
  - rubygems: ≥8 repos (≥5%)
- No forks or duplicates
- High-quality repositories (stars, recent activity)

## Phase 2: Pre-Expansion Backup

The orchestrator automatically creates a backup before ingestion. To manually create a backup:

```bash
python scripts/backup_database.py --db-path data/graphs.db --output-dir backups
```

Verify backup:

```bash
ls -lh backups/
# Should show backup file with timestamp
```

## Phase 3: Batch Ingestion

### Preflight Validation (Recommended)

Test ingestion on a small subset (10 repos) before full run:

```bash
# Extract first 10 repos from selection
cat data/expansion_reports/selection_*.json | jq '.repositories[:10]' > data/expansion_reports/preflight_selection.json

# Run ingestion on subset
python scripts/ingest_with_dependencies.py --repo-list data/expansion_reports/preflight_selection.json
```

Verify preflight results:
- Resolution rate ≥85%
- Ecosystem classification correct
- No critical errors

### Full Expansion

If preflight passes, run full expansion:

```bash
python scripts/expand_dataset.py expand --target-count 200
```

This will:
- Create pre-expansion backup
- Select 149 repositories
- Execute batch ingestion (24 hours)
- Monitor progress with ETA
- Log failures and continue

### Monitor Progress

The orchestrator displays real-time progress:

```
[████████████████░░░░░░░░░░░░░░] 55.0% | 82/149 | ✅ owner/repo | ETA: 2h 15m
Success: 78 | Failed: 4 | Resolution: 87.3% | Deps: 12,450
```

Monitor logs:

```bash
tail -f logs/expansion.log
```

## Phase 4: Validation

After ingestion completes, run validation suite:

```bash
python scripts/validate_expansion.py --db-path data/graphs.db --expected-repo-count 200
```

Validation checks:
- ✅ Repository count == 200
- ✅ Dependency count in [15,000, 50,000]
- ✅ Resolution rate ≥ 85%
- ✅ Ecosystem count ≥ 5
- ✅ Ecosystem distribution meets targets
- ✅ Query performance < 5 seconds (p95)

If validation fails, see [Troubleshooting](#troubleshooting) section.

## Phase 5: Signal Quality Analysis

Analyze cross-repository insights:

```bash
python scripts/analyze_insights.py --db-path data/graphs.db --baseline-repo-count 51
```

This identifies:
- Hub packages (used by >25% of repos)
- Largest transitive footprints
- Ecosystem-specific patterns
- Duplicate dependency graphs

Verify:
- ✅ At least 5 new insights discovered
- ✅ Hub packages identified
- ✅ Ecosystem patterns detected

## Phase 6: Reporting

Generate comprehensive expansion report:

```bash
python scripts/generate_expansion_report.py \
  --db-path data/graphs.db \
  --repos-added 149 \
  --repos-failed 0
```

Report includes:
- Executive summary
- Newly added repositories
- Failed ingestions (if any)
- Ecosystem distribution
- Query performance metrics
- Cross-repository insights
- Duplicate graph detection
- Validation status

Review report:

```bash
cat data/expansion_reports/expansion_report_*.md
```

## Rollback Procedure

If validation fails or issues are discovered, rollback to pre-expansion state:

### Step 1: Identify Backup

```bash
ls -lh backups/
# Find the backup created before expansion
```

### Step 2: Execute Rollback

```bash
python scripts/expand_dataset.py rollback \
  --backup-path backups/graphs_TIMESTAMP.db \
  --db-path data/graphs.db \
  --expected-repo-count 51
```

This will:
1. Verify backup integrity
2. Restore database from backup
3. Verify restored repo count
4. Rebuild indexes

### Step 3: Verify Rollback

```bash
python scripts/validate_expansion.py --expected-repo-count 51
```

## Troubleshooting

### Validation Failures

#### Low Resolution Rate (<85%)

**Symptoms:**
- Resolution rate below 85%
- Many dependencies unresolved

**Diagnosis:**
```bash
# Check unresolved dependencies
sqlite3 data/graphs.db "SELECT COUNT(*) FROM repo_dependencies WHERE resolved_repo IS NULL"
```

**Solutions:**
1. Check package resolver configuration
2. Verify registry API access
3. Review failed resolution logs
4. Consider re-running ingestion for failed repos

#### Ecosystem Distribution Violations

**Symptoms:**
- Ecosystem percentages outside target ranges
- Too few repositories in required ecosystems

**Diagnosis:**
```bash
# Check ecosystem distribution
python scripts/analyze_insights.py --db-path data/graphs.db | grep -A 10 "Ecosystem Distribution"
```

**Solutions:**
1. Review selection criteria
2. Adjust ecosystem targets in SelectionCriteria
3. Re-run selection with updated criteria
4. Manually add repositories from underrepresented ecosystems

#### Query Performance Degradation

**Symptoms:**
- Queries taking >5 seconds
- Slow API responses

**Diagnosis:**
```bash
# Run performance benchmark
python scripts/validate_expansion.py --db-path data/graphs.db | grep -A 20 "Query Performance"
```

**Solutions:**
1. Rebuild indexes: `python scripts/rebuild_indexes.py --optimize`
2. Analyze slow queries
3. Add missing indexes
4. Consider database optimization

#### Insufficient Signal Quality (<5 insights)

**Symptoms:**
- Fewer than 5 cross-repository insights
- No hub packages detected
- Limited ecosystem patterns

**Diagnosis:**
```bash
python scripts/analyze_insights.py --db-path data/graphs.db
```

**Solutions:**
1. Review repository selection diversity
2. Check for duplicate graphs
3. Verify dependency data quality
4. Consider adding more diverse repositories

### Ingestion Failures

#### GitHub API Rate Limiting

**Symptoms:**
- 403/429 errors
- "Rate limit exceeded" messages

**Solutions:**
1. Wait for rate limit reset (check X-RateLimit-Reset header)
2. Use authenticated requests (GITHUB_TOKEN)
3. Implement exponential backoff (already built-in)
4. Spread ingestion over multiple days

#### Manifest Parsing Errors

**Symptoms:**
- "Manifest not found" errors
- "Failed to parse manifest" errors

**Solutions:**
1. Check repository structure
2. Verify manifest file locations
3. Review parser logs
4. Skip problematic repositories

#### Database Write Failures

**Symptoms:**
- "Database locked" errors
- "Disk full" errors

**Solutions:**
1. Check disk space: `df -h`
2. Close other database connections
3. Increase WAL checkpoint frequency
4. Use larger disk

## Best Practices

### Before Expansion

1. ✅ Run dry run to review selection
2. ✅ Verify sufficient disk space
3. ✅ Create manual backup
4. ✅ Run preflight validation on 10-repo subset
5. ✅ Review GitHub API rate limits

### During Expansion

1. ✅ Monitor progress regularly
2. ✅ Check logs for errors
3. ✅ Track resolution rate
4. ✅ Note any failed repositories

### After Expansion

1. ✅ Run full validation suite
2. ✅ Analyze signal quality
3. ✅ Generate expansion report
4. ✅ Review duplicate graphs
5. ✅ Update documentation

## Command Reference

### Expansion

```bash
# Dry run (selection only)
python scripts/expand_dataset.py expand --dry-run

# Full expansion
python scripts/expand_dataset.py expand --target-count 200

# Custom backup directory
python scripts/expand_dataset.py expand --backup-dir /var/backups
```

### Validation

```bash
# Full validation
python scripts/validate_expansion.py --db-path data/graphs.db

# Specific checks
python scripts/validate_expansion.py --expected-repo-count 200 --min-resolution-rate 0.85
```

### Analysis

```bash
# Insight analysis
python scripts/analyze_insights.py --db-path data/graphs.db

# JSON output
python scripts/analyze_insights.py --json --output insights.json
```

### Reporting

```bash
# Generate report
python scripts/generate_expansion_report.py --db-path data/graphs.db

# Custom output
python scripts/generate_expansion_report.py --output custom_report.md
```

### Rollback

```bash
# Rollback to backup
python scripts/expand_dataset.py rollback --backup-path backups/graphs_TIMESTAMP.db

# Verify rollback
python scripts/validate_expansion.py --expected-repo-count 51
```

## Timeline

Typical expansion timeline:

- **Phase 1 (Selection):** 30 minutes
- **Phase 2 (Backup):** 5 minutes
- **Phase 3 (Ingestion):** 24 hours
- **Phase 4 (Validation):** 15 minutes
- **Phase 5 (Analysis):** 10 minutes
- **Phase 6 (Reporting):** 5 minutes

**Total:** ~24-25 hours

## Success Criteria

Expansion is successful when:

- ✅ 200 repositories ingested
- ✅ Resolution rate ≥ 85%
- ✅ Query performance < 5 seconds (p95)
- ✅ Ecosystem distribution meets all targets
- ✅ At least 5 new cross-repository insights
- ✅ All validation checks pass
- ✅ Expansion report generated

## Support

For issues or questions:

1. Check logs: `logs/expansion.log`
2. Review validation report
3. Consult troubleshooting section
4. Check GitHub issues
5. Contact development team

## Appendix

### Selection Criteria

Default selection criteria:

```python
SelectionCriteria(
    min_stars=1000,
    min_commit_age_days=180,  # 6 months
    required_ecosystems=['npm', 'pypi', 'go', 'maven', 'rubygems'],
    ecosystem_targets={
        'npm': (0.25, 0.40),
        'pypi': (0.25, 0.40),
        'go': (0.10, 1.0),
        'maven': (0.10, 1.0),
        'rubygems': (0.05, 1.0)
    },
    exclude_forks=True
)
```

### Priority Score Calculation

```
score = 0.4 * stars_score + 
        0.3 * recency_score + 
        0.2 * prod_deps_score +
        0.1 * ecosystem_diversity_bonus
```

### Resolution Definition

A dependency is resolved if:
1. Package is matched to a registry (registry_type IS NOT NULL)
2. Version is successfully parsed (specifier IS NOT NULL)
3. Registry metadata is retrieved (resolved_repo IS NOT NULL)

### Query Performance Patterns

Benchmarked query patterns:
1. Single repo dependencies
2. Package dependents
3. Hub packages
4. Cross-repo search
5. Ecosystem distribution
6. Resolution rate
7. Top packages
8. Transitive dependencies
9. Aggregate stats
10. Package metadata
