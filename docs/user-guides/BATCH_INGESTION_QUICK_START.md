# Batch Ingestion Quick Start

Get started with batch ingestion in 5 minutes.

## Prerequisites

```bash
# Ensure dependencies installed
pip install -e ".[dev]"

# Optional: Add GitHub token for higher rate limits
echo "GITHUB_TOKEN=ghp_your_token_here" >> .env
```

## Basic Usage

### 1. Test with 3 repos

```bash
python -m open_source_risk_model.cli.ingest \
  --input data/repos_test.txt
```

### 2. Ingest full dataset (51 repos)

```bash
python -m open_source_risk_model.cli.ingest \
  --input data/repos_full.txt \
  --resume \
  --sleep-on-ratelimit
```

### 3. Ingest with concurrency (faster)

```bash
python -m open_source_risk_model.cli.ingest \
  --input data/repos_full.txt \
  --concurrency 3 \
  --resume \
  --sleep-on-ratelimit
```

## Output

### Progress Bar

```
[████████████████░░░░░░░░░░░░░░] 55.0% | 28/51 | ✅ pallets/flask | ETA: 2m | 15 deps, 93% resolved
```

### Summary

```
================================================================================
INGESTION SUMMARY
================================================================================
Total repos:      51
Successful:       48 (94.1%)
Failed:           2 (3.9%)
Skipped:          1 (2.0%)
Duration:         15m
Rate:             0.06 repos/sec
================================================================================
```

### Manifest

Check `data/manifest.json` for detailed results:

```bash
cat data/manifest.json | jq .summary
```

## Common Commands

### Resume interrupted run

```bash
python -m open_source_risk_model.cli.ingest \
  --input data/repos_full.txt \
  --resume
```

### Limit to 100 repos

```bash
python -m open_source_risk_model.cli.ingest \
  --input data/repos_full.txt \
  --max-repos 100
```

### Debug mode

```bash
python -m open_source_risk_model.cli.ingest \
  --input data/repos_test.txt \
  --log-level DEBUG
```

## Troubleshooting

### Rate limit errors

Add GitHub token to `.env`:

```bash
echo "GITHUB_TOKEN=ghp_your_token_here" >> .env
```

### Check progress

```bash
sqlite3 data/graphs.db "SELECT status, COUNT(*) FROM repo_ingestion_runs GROUP BY status"
```

### View manifest

```bash
cat data/manifest.json | jq .
```

## Next Steps

1. Validate data: `python scripts/generate_dataset_report.py`
2. Test queries: `./demo_query_api.sh`
3. View in UI: `open ui/query.html`

## Full Documentation

See [BATCH_INGESTION_GUIDE.md](BATCH_INGESTION_GUIDE.md) for complete documentation.
