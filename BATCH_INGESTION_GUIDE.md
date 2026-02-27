# Batch Ingestion Guide

Complete guide for ingesting 100-500 repositories with the new batch ingestion CLI.

## Overview

The batch ingestion CLI provides production-ready features for ingesting large datasets:

- **Progress tracking** - Real-time progress bar with ETA
- **Resume capability** - Skip already-ingested repos
- **Rate limit handling** - Automatic detection and exponential backoff
- **Concurrency** - Multiple workers with rate limit coordination
- **Dataset manifest** - JSON manifest with ingestion metadata
- **Per-repo status** - Detailed success/failure reporting

## Quick Start

### 1. Prepare Repository List

Create a text file with one repository per line:

```bash
# repos.txt
pallets/flask
django/django
fastapi/fastapi
psf/requests
# ... more repos
```

### 2. Run Batch Ingestion

Basic usage:

```bash
python -m open_source_risk_model.cli.ingest \
  --input repos.txt \
  --resume \
  --sleep-on-ratelimit
```

With concurrency:

```bash
python -m open_source_risk_model.cli.ingest \
  --input repos.txt \
  --concurrency 3 \
  --resume \
  --sleep-on-ratelimit
```

Limit number of repos:

```bash
python -m open_source_risk_model.cli.ingest \
  --input repos.txt \
  --max-repos 100 \
  --resume
```

## Command-Line Options

### Required

- `--input FILE` - Input file with repository list (one per line)

### Optional

- `--db-path PATH` - Path to database (default: `data/graphs.db`)
- `--max-repos N` - Maximum number of repos to ingest
- `--concurrency N` - Number of concurrent workers (default: 1)
- `--resume` - Skip already-ingested repos
- `--sleep-on-ratelimit` - Sleep and retry on rate limit (instead of failing)
- `--manifest-output PATH` - Output path for dataset manifest (default: `data/manifest.json`)
- `--log-level LEVEL` - Logging level: DEBUG, INFO, WARNING, ERROR (default: INFO)

## Features

### Progress Tracking

Real-time progress bar with:
- Percentage complete
- Repos processed / total
- Current repo status (✅ success, ❌ failed, ⏭️ skipped)
- Estimated time remaining
- Per-repo details (dependencies found, resolution rate)

Example output:

```
[████████████████░░░░░░░░░░░░░░] 55.0% | 28/51 | ✅ pallets/flask | ETA: 2m | 15 deps, 93% resolved
```

### Resume Capability

The `--resume` flag enables idempotent ingestion:

- Tracks ingestion runs in `repo_ingestion_runs` table
- Skips repos already successfully ingested in current run
- Retries failed repos from previous runs
- Safe to interrupt and restart

**Use case**: Ingest 500 repos overnight, resume if interrupted

```bash
# Start ingestion
python -m open_source_risk_model.cli.ingest --input repos_500.txt --resume

# If interrupted, just run again
python -m open_source_risk_model.cli.ingest --input repos_500.txt --resume
```

### Rate Limit Handling

GitHub API has rate limits:
- **Unauthenticated**: 60 requests/hour
- **Authenticated**: 5,000 requests/hour
- **Secondary rate limits**: Triggered by rapid requests

The CLI handles rate limits automatically:

1. **Detection** - Recognizes 403/429 responses and rate limit errors
2. **Exponential backoff** - Waits 60s, 120s, 240s with jitter
3. **Retry** - Retries up to 3 times per repo
4. **Coordination** - Concurrent workers share rate limit budget

**Recommendation**: Use `--sleep-on-ratelimit` for large batches

```bash
python -m open_source_risk_model.cli.ingest \
  --input repos_500.txt \
  --concurrency 3 \
  --sleep-on-ratelimit \
  --resume
```

### Concurrency

Multiple workers can ingest repos in parallel:

- `--concurrency 1` - Sequential (default, safest)
- `--concurrency 2-4` - Recommended for 100+ repos
- `--concurrency 5+` - May trigger rate limits

**Trade-offs**:
- Higher concurrency = faster ingestion
- Higher concurrency = more likely to hit rate limits
- Use `--sleep-on-ratelimit` with concurrency > 1

**Recommendation**: Start with 2-3 workers

```bash
python -m open_source_risk_model.cli.ingest \
  --input repos_500.txt \
  --concurrency 3 \
  --sleep-on-ratelimit \
  --resume
```

### Dataset Manifest

After ingestion, a JSON manifest is written to `data/manifest.json`:

```json
{
  "version": "1.0",
  "generated_at": "2026-02-27T10:30:00Z",
  "run_id": "run-20260227-103000-a1b2c3d4",
  "repos": [
    {
      "repo_full_name": "pallets/flask",
      "status": "success",
      "dependencies_found": 15,
      "dependencies_resolved": 14,
      "manifests_discovered": 2,
      "resolution_rate": 0.93,
      "duration_seconds": 5.2,
      "ingested_at": "2026-02-27T10:30:05Z",
      "errors": []
    }
  ],
  "skipped": [
    {
      "repo_full_name": "django/django",
      "reason": "already_ingested"
    }
  ],
  "summary": {
    "total_repos": 51,
    "successful_repos": 48,
    "failed_repos": 2,
    "skipped_repos": 1,
    "total_dependencies": 3674,
    "total_resolved": 3278,
    "resolution_rate": 0.892
  }
}
```

**Use cases**:
- Cross-repo queries (which repos have X dependency?)
- Quality reporting (resolution rates, failure analysis)
- Audit trail (when was each repo ingested?)
- Dataset versioning (track ingestion runs over time)

## Best Practices

### For 100-500 Repos

1. **Use GitHub token** - Set `GITHUB_TOKEN` in `.env` for 5,000 req/hour
2. **Start with low concurrency** - Use 2-3 workers initially
3. **Enable resume** - Always use `--resume` for large batches
4. **Handle rate limits** - Use `--sleep-on-ratelimit`
5. **Monitor progress** - Watch for patterns in failures

```bash
# Recommended command for 100-500 repos
python -m open_source_risk_model.cli.ingest \
  --input repos_full.txt \
  --concurrency 3 \
  --resume \
  --sleep-on-ratelimit \
  --log-level INFO
```

### For Testing

1. **Use small dataset** - Test with 3-5 repos first
2. **No concurrency** - Use default sequential mode
3. **Check manifest** - Verify output format

```bash
# Test command
python -m open_source_risk_model.cli.ingest \
  --input data/repos_test.txt \
  --log-level DEBUG
```

### For Production

1. **Run overnight** - Large batches take hours
2. **Use screen/tmux** - Prevent interruption from SSH disconnect
3. **Monitor logs** - Check for rate limit patterns
4. **Validate manifest** - Review summary after completion

```bash
# Production command (in screen/tmux)
python -m open_source_risk_model.cli.ingest \
  --input repos_500.txt \
  --concurrency 3 \
  --resume \
  --sleep-on-ratelimit \
  --manifest-output data/manifest_$(date +%Y%m%d).json \
  --log-level INFO
```

## Troubleshooting

### Rate Limit Errors

**Symptom**: Many repos failing with "Rate limit exceeded"

**Solutions**:
1. Add `GITHUB_TOKEN` to `.env` file
2. Use `--sleep-on-ratelimit` flag
3. Reduce `--concurrency` to 1-2
4. Wait 1 hour and resume

### Slow Ingestion

**Symptom**: < 0.1 repos/second

**Solutions**:
1. Increase `--concurrency` to 2-4
2. Check network connection
3. Verify GitHub API is responsive

### High Failure Rate

**Symptom**: > 10% repos failing

**Solutions**:
1. Check repo list format (owner/repo)
2. Verify repos exist and are public
3. Review error messages in manifest
4. Check database disk space

### Interrupted Ingestion

**Symptom**: Process killed or interrupted

**Solutions**:
1. Just run again with `--resume` flag
2. Check manifest for progress
3. Review `repo_ingestion_runs` table

```bash
# Check progress in database
sqlite3 data/graphs.db "SELECT status, COUNT(*) FROM repo_ingestion_runs GROUP BY status"
```

## Performance Expectations

### Timing

- **Per repo**: 3-10 seconds (depends on manifest count)
- **100 repos**: 10-30 minutes (with concurrency=3)
- **500 repos**: 1-3 hours (with concurrency=3)

### Rate Limits

- **Without token**: ~50 repos/hour (60 req/hour limit)
- **With token**: ~300 repos/hour (5,000 req/hour limit)
- **With concurrency=3**: ~900 repos/hour (theoretical max)

### Resolution Rates

- **Expected**: 85-95% (depends on ecosystem)
- **Python (PyPI)**: 90-95%
- **JavaScript (npm)**: 85-90%
- **Mixed**: 85-92%

## Database Schema

### repo_ingestion_runs Table

Tracks individual repo ingestion attempts:

```sql
CREATE TABLE repo_ingestion_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_full_name TEXT NOT NULL,
    run_id TEXT NOT NULL,
    status TEXT NOT NULL,  -- success, failed, in_progress
    started_at TEXT NOT NULL,
    completed_at TEXT,
    dependencies_found INTEGER DEFAULT 0,
    dependencies_resolved INTEGER DEFAULT 0,
    manifests_discovered INTEGER DEFAULT 0,
    error_message TEXT,
    duration_seconds REAL,
    UNIQUE(repo_full_name, run_id)
);
```

### Query Examples

Check ingestion status:

```sql
-- Summary by status
SELECT status, COUNT(*) as count
FROM repo_ingestion_runs
WHERE run_id = 'run-20260227-103000-a1b2c3d4'
GROUP BY status;

-- Failed repos
SELECT repo_full_name, error_message
FROM repo_ingestion_runs
WHERE status = 'failed'
ORDER BY started_at DESC;

-- Resolution rates
SELECT 
    repo_full_name,
    dependencies_found,
    dependencies_resolved,
    ROUND(dependencies_resolved * 100.0 / dependencies_found, 1) as resolution_pct
FROM repo_ingestion_runs
WHERE status = 'success' AND dependencies_found > 0
ORDER BY resolution_pct DESC;
```

## Next Steps

After successful batch ingestion:

1. **Validate data quality** - Run `python scripts/generate_dataset_report.py`
2. **Test queries** - Try cross-repo queries via API
3. **Update UI** - Refresh UI to show new repos
4. **Schedule updates** - Set up periodic re-ingestion

## Examples

### Example 1: Test Run (3 repos)

```bash
python -m open_source_risk_model.cli.ingest \
  --input data/repos_test.txt \
  --log-level DEBUG
```

Expected output:

```
Loading repos from data/repos_test.txt...
Loaded 3 repos
Initializing database at data/graphs.db...
Run ID: run-20260227-103000-a1b2c3d4

Starting ingestion with 1 worker(s)...
================================================================================
[██████████████████████████████] 100.0% | 3/3 | ✅ fastapi/fastapi | ETA: 0s | 12 deps, 91% resolved

================================================================================
INGESTION SUMMARY
================================================================================
Total repos:      3
Successful:       3 (100.0%)
Failed:           0 (0.0%)
Skipped:          0 (0.0%)
Duration:         15s
Rate:             0.20 repos/sec
================================================================================

Writing dataset manifest to data/manifest.json...

✅ Ingestion complete!
   Run ID: run-20260227-103000-a1b2c3d4
   Manifest: data/manifest.json
```

### Example 2: Production Run (500 repos)

```bash
python -m open_source_risk_model.cli.ingest \
  --input data/repos_full.txt \
  --max-repos 500 \
  --concurrency 3 \
  --resume \
  --sleep-on-ratelimit \
  --manifest-output data/manifest_20260227.json
```

Expected output:

```
Loading repos from data/repos_full.txt...
Loaded 500 repos
Initializing database at data/graphs.db...
Run ID: run-20260227-103000-a1b2c3d4

Starting ingestion with 3 worker(s)...
================================================================================
[████████████████░░░░░░░░░░░░░░] 55.0% | 275/500 | ✅ django/django | ETA: 45m | 28 deps, 89% resolved
```

## Support

For issues or questions:

1. Check troubleshooting section above
2. Review logs with `--log-level DEBUG`
3. Inspect database: `sqlite3 data/graphs.db`
4. Check manifest: `cat data/manifest.json | jq .summary`

## Related Documentation

- [WEEK_2_3_COMPLETE.md](WEEK_2_3_COMPLETE.md) - Query API implementation
- [PROJECT_NORTH_STAR.md](PROJECT_NORTH_STAR.md) - Project vision and principles
- [docs/API.md](docs/API.md) - API reference
