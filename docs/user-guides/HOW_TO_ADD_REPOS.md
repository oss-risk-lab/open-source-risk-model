# How to Add Repositories to the Database

## The Problem You Encountered

When you ran `select_expansion_repos.py`, it only **selected** repositories and saved them to a JSON file. It didn't actually **ingest** them into the database, which is why you couldn't see them in the query interface.

## Two-Step Workflow

### Step 1: Select Repositories ✅

This finds high-quality repos based on criteria (stars, recency, ecosystem):

```bash
python scripts/select_expansion_repos.py \
  --count 100 \
  --min-stars 1000 \
  --output /tmp/selected_repos.json
```

**Output:** JSON file with candidate repositories

### Step 2: Ingest Repositories into Database ✅

This actually adds the repos to your database:

```bash
# Convert JSON to text file (one repo per line)
cat /tmp/selected_repos.json | python -c "
import json, sys
data = json.load(sys.stdin)
for repo in data['repositories'][:10]:  # First 10 repos
    print(repo['full_name'])
" > /tmp/repos_to_ingest.txt

# Ingest into database
PYTHONPATH=. python -m open_source_risk_model.cli.ingest \
  --input /tmp/repos_to_ingest.txt \
  --db-path data/graphs.db \
  --resume \
  --log-level INFO
```

## Quick Test (What We Just Did)

```bash
# 1. Selected 114 repos
python scripts/select_expansion_repos.py --count 10 --output /tmp/test_selection.json

# 2. Extracted first 5 repos to text file
cat /tmp/test_selection.json | python -c "
import json, sys
data = json.load(sys.stdin)
for repo in data['repositories'][:5]:
    print(repo['full_name'])
" > /tmp/test_5_repos.txt

# 3. Ingested them
PYTHONPATH=. python -m open_source_risk_model.cli.ingest \
  --input /tmp/test_5_repos.txt \
  --db-path data/graphs.db \
  --resume
```

**Result:** 5 new repos added to database (10 → 15 total)

## Verify in Query Interface

### Option 1: Dataset Stats Button

1. Open `http://localhost:8000/ui/query.html`
2. Click "Dataset Stats" button
3. See updated repo count

### Option 2: Search Repos

1. In query interface, use intent: `search_repos`
2. Parameters: `{"pattern": "%three%"}`
3. See newly added repos like `mrdoob/three.js`

### Option 3: Command Line

```bash
PYTHONPATH=. python -c "
from open_source_risk_model.query.intent_executor import IntentExecutor
executor = IntentExecutor('data/graphs.db')
result = executor.execute('dataset_stats', {})
print(f\"Repo count: {result.results[0]['repo_count']}\")
"
```

## Current Database Status

**Before ingestion:**
- Repo count: 10
- Dependencies: 3,313
- Resolution rate: 88.6%

**After ingestion (5 new repos):**
- Repo count: 56
- Dependencies: 3,889
- Resolution rate: 89.5%

## Full Expansion Workflow

For a complete dataset expansion to 400-500 repos:

```bash
# 1. Select repos (takes ~1 minute)
python scripts/select_expansion_repos.py \
  --count 400 \
  --min-stars 1000 \
  --output data/expansion/phase_a_repos.json

# 2. Convert to text file
cat data/expansion/phase_a_repos.json | python -c "
import json, sys
data = json.load(sys.stdin)
for repo in data['repositories']:
    print(repo['full_name'])
" > data/expansion/phase_a_repos.txt

# 3. Preflight test (10 repos)
head -10 data/expansion/phase_a_repos.txt > data/expansion/preflight.txt
PYTHONPATH=. python -m open_source_risk_model.cli.ingest \
  --input data/expansion/preflight.txt \
  --db-path data/graphs.db \
  --resume

# 4. If preflight passes, run full ingestion
PYTHONPATH=. python -m open_source_risk_model.cli.ingest \
  --input data/expansion/phase_a_repos.txt \
  --db-path data/graphs.db \
  --resume \
  --sleep-on-ratelimit
```

## Ingestion Options

```bash
--input FILE              # Input file (one repo per line)
--db-path PATH            # Database path (default: data/graphs.db)
--resume                  # Skip already-ingested repos
--sleep-on-ratelimit      # Wait and retry on GitHub rate limits
--concurrency N           # Number of parallel workers (default: 1)
--max-repos N             # Limit number of repos to ingest
--log-level LEVEL         # DEBUG, INFO, WARNING, ERROR
```

## Troubleshooting

### "Why can't I see the repos?"

You only ran Step 1 (selection). You need Step 2 (ingestion).

### "How long does ingestion take?"

- Small repos (10-20 deps): ~5-10 seconds
- Large repos (100+ deps): ~30-60 seconds
- 100 repos: ~30-60 minutes
- 400 repos: ~2-4 hours

### "Can I resume if it fails?"

Yes! Use `--resume` flag. It skips already-ingested repos.

### "What if I hit rate limits?"

Use `--sleep-on-ratelimit` flag. It will wait and retry automatically.

## Summary

**Selection** = Finding good repos (fast, ~1 minute)  
**Ingestion** = Adding them to database (slow, ~1 hour per 100 repos)

You need both steps for repos to appear in the query interface!
