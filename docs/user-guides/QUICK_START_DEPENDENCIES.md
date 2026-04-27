# Quick Start: Populate Real Dependencies 🚀

## TL;DR

```bash
# 1. Ingest some popular repos (takes ~30 seconds)
python scripts/ingest_with_dependencies.py \
  numpy/numpy \
  fastapi/fastapi \
  facebook/react

# 2. Refresh your Dependency Explorer UI
# Now these repos will show real dependencies!
```

## The Best Process

### Option 1: Ingestion Script (Recommended) ⭐

**Use this for**: Populating real data quickly and reliably

```bash
# Single repo
python scripts/ingest_with_dependencies.py numpy/numpy

# Multiple repos
python scripts/ingest_with_dependencies.py numpy/numpy scipy/scipy pandas-dev/pandas

# From file
python scripts/ingest_with_dependencies.py --file repos_to_ingest.txt
```

**What it does**:
1. ✅ Fetches repo from GitHub
2. ✅ Discovers ALL manifest files
3. ✅ Parses ALL dependencies
4. ✅ Resolves packages to repos
5. ✅ Stores in database
6. ✅ Shows progress and results

### Option 2: Graph API (Automatic)

**Use this for**: Automatic ingestion when viewing graphs

```bash
# Just generate a graph - dependencies are parsed automatically
curl "http://localhost:8000/api/graph?repo=numpy/numpy"
```

Then query dependencies:
```bash
curl "http://localhost:8000/api/repos/numpy/numpy/dependencies"
```

### Option 3: Batch API (Background)

**Use this for**: Large batches processed in background

```bash
curl -X POST "http://localhost:8000/api/ingest" \
  -H "Content-Type: application/json" \
  -d '{"repos": ["numpy/numpy", "scipy/scipy"]}'
```

## Quick Demo

Let's populate 3 repos right now:

```bash
# This will take about 15-20 seconds
python scripts/ingest_with_dependencies.py \
  numpy/numpy \
  fastapi/fastapi \
  facebook/react

# Output will show:
# - Manifests discovered
# - Dependencies parsed
# - Packages resolved
# - Success summary
```

After this, try in your UI:
- `numpy/numpy` - Will show Python dependencies
- `fastapi/fastapi` - Will show Python dependencies
- `facebook/react` - Will show JavaScript dependencies

## Files Created

1. **`scripts/ingest_with_dependencies.py`** - Main ingestion script
2. **`repos_to_ingest.txt`** - Sample list of popular repos
3. **`DEPENDENCY_INGESTION_GUIDE.md`** - Complete guide
4. **`QUICK_START_DEPENDENCIES.md`** - This file

## Comparison: Test Data vs Real Data

### Current (Test Data)
```
pallets/flask: 4 dependencies
django/django: 1 dependency
psf/requests: 1 dependency
```

### After Ingestion (Real Data)
```
numpy/numpy: ~20-30 dependencies
fastapi/fastapi: ~15-20 dependencies
facebook/react: ~10-15 dependencies
```

Much more realistic!

## Next Steps

1. **Try it now**:
   ```bash
   python scripts/ingest_with_dependencies.py numpy/numpy
   ```

2. **Check the results**:
   ```bash
   curl "http://localhost:8000/api/repos/numpy/numpy/dependencies"
   ```

3. **View in UI**:
   - Open `ui/dependency-explorer.html`
   - Enter `numpy/numpy`
   - See real dependencies!

4. **Populate more**:
   ```bash
   python scripts/ingest_with_dependencies.py --file repos_to_ingest.txt
   ```

## Why This Approach?

✅ **Complete**: Gets ALL dependencies, not just samples
✅ **Accurate**: Parses actual manifest files from GitHub
✅ **Reliable**: Handles errors gracefully
✅ **Fast**: 2-5 seconds per repo
✅ **Trackable**: Shows progress and results
✅ **Reusable**: Can re-run to update data

## Common Questions

**Q: How long does it take?**
A: 2-5 seconds per repository. 10 repos = ~30-50 seconds.

**Q: Do I need a GitHub token?**
A: Recommended but not required. Without it, you're limited to 60 requests/hour.

**Q: Can I automate this?**
A: Yes! Set up a cron job to run the script daily/weekly.

**Q: What if a repo has no dependencies?**
A: The script will report 0 dependencies - that's fine!

**Q: Can I ingest private repos?**
A: Yes, if your GitHub token has access to them.

## Ready to Go!

The best process is:

```bash
# Set token (optional but recommended)
export GITHUB_TOKEN=your_token_here

# Ingest repos
python scripts/ingest_with_dependencies.py \
  numpy/numpy \
  django/django \
  fastapi/fastapi \
  facebook/react \
  expressjs/express

# Enjoy real data in your UI! 🎉
```

See `DEPENDENCY_INGESTION_GUIDE.md` for complete documentation.

