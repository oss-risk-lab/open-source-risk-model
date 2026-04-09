# 🚀 Week 1 Quick Reference

## One-Command Execution

```bash
# Run pilot (10 repos) with quality gate
./scripts/ingest_dataset.sh pilot

# If pilot passes, run full dataset (50 repos)
./scripts/ingest_dataset.sh full
```

## Files Created

| File | Purpose |
|------|---------|
| `data/repos_pilot.txt` | 10 repos for pilot |
| `data/repos_full.txt` | 50 repos for full dataset |
| `scripts/ingest_dataset.sh` | Ingestion command |
| `scripts/generate_dataset_report.py` | Quality report generator |

## Quality Gate Criteria

| Criterion | Threshold | Measures |
|-----------|-----------|----------|
| Manifest Coverage | ≥80% | Discovery effectiveness |
| Dependency Coverage | ≥70% | Parsing effectiveness |
| Resolution Rate | ≥75% | Package → GitHub mapping |
| Error Rate | ≤20% | Overall health |

## Expected Results

### Pilot (10 repos)
- Duration: 10-15 minutes
- Dependencies: 200-300
- Resolution rate: 85-90%

### Full (50 repos)
- Duration: 45-60 minutes
- Dependencies: 1000-2000
- Resolution rate: 85-90%

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Rate limit | Set `GITHUB_TOKEN` in `.env` |
| Gate fails | Review report, fix issues, re-run pilot |
| Parser errors | Check manifest type distribution |
| Slow ingestion | Check network, API limits |

## Next Steps

1. ✅ Run pilot
2. ✅ Pass quality gate
3. ✅ Run full ingestion
4. ✅ Validate metrics
5. → Proceed to Week 2 (Intent API)
