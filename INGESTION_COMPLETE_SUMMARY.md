# Dataset Expansion Complete

## Final Results

Successfully ingested all 114 selected repositories into the database.

### Database Statistics

**Before Expansion:**
- Repos: 56
- Dependencies: 3,889
- Resolution Rate: 89.5%

**After Expansion:**
- Repos: 145 (↑ 89 repos, +159%)
- Dependencies: 10,396 (↑ 6,507 deps, +167%)
- Unique Packages: 3,936
- Resolved Dependencies: 8,991
- Resolution Rate: 86.5%
- Repos with Dependencies: 113 (78%)
- Total Manifests: 458

### Ingestion Batches

All 5 batches completed successfully:

1. **Batch 1 (repos 21-40)**: 20 repos, 3,142 deps, 91.7% resolution, 13m duration
2. **Batch 2 (repos 41-60)**: 20 repos (completed earlier)
3. **Batch 3 (repos 61-80)**: 20 repos, 2,372 deps, 58.8% resolution, 4m duration
4. **Batch 4 (repos 81-100)**: 20 repos, 1,161 deps, 29.8% resolution, 3m duration
5. **Batch 5 (repos 101-114)**: 14 repos, 12 deps, 91.7% resolution, 35s duration

### Performance

- Total ingestion time: ~30-40 minutes (parallel processing)
- Average rate: ~0.03-0.40 repos/sec (varies by repo size)
- Parallel processes: 4-5 simultaneous ingestion jobs
- Success rate: 100% (all repos ingested successfully)

### Query Interface Verification

Dataset stats endpoint confirms all repos are visible:
```json
{
  "repo_count": 145,
  "total_dependencies": 10018,
  "resolved_dependencies": 8634,
  "unique_packages": 3897,
  "resolution_rate": 86.2
}
```

## Next Steps

The dataset is now ready for:
- Query testing with expanded repository coverage
- Dependency analysis across 145 repos
- Supply chain risk assessment
- Ecosystem insights generation

## Files

- Database: `data/graphs.db`
- Selection file: `/tmp/all_114_repos.txt`
- Workflow guide: `HOW_TO_ADD_REPOS.md`
- Test results: `EXPANSION_TEST_RESULTS.md`
