# 📊 Week 1: Data Population - Implementation Guide

**Goal**: Populate 50 repos with quality-gated pilot approach
**Timeline**: 3-5 days
**Status**: Ready to execute

---

## 🎯 Deliverables

### 1. Repository Lists ✅
- **`data/repos_pilot.txt`** - 10 repos for pilot (optimized for overlap)
- **`data/repos_full.txt`** - 50 repos for full dataset (optimized for ecosystem coverage)

### 2. Ingestion Command ✅
- **`scripts/ingest_dataset.sh`** - Automated ingestion with quality gate

### 3. Dataset Report ✅
- **`scripts/generate_dataset_report.py`** - Comprehensive quality metrics

---

## 📋 Execution Plan

### Phase 1: Pilot Ingestion (10 repos)

**Command**:
```bash
./scripts/ingest_dataset.sh pilot
```

**What it does**:
1. Ingests 10 carefully selected repos
2. Discovers manifests (requirements.txt, package.json, etc.)
3. Parses dependencies
4. Resolves packages to GitHub repos
5. Generates dataset report
6. Evaluates quality gate

**Expected Duration**: 10-15 minutes

**Expected Output**:
```
INGESTION SUMMARY
Total repos: 10
Successful: 9-10
Total dependencies: 200-300
Total resolved: 180-270 (85-90%)

QUALITY GATE
Status: ✅ PASSED

✅ At least 80% of repos have manifests
   Value: 90.0% | Threshold: 80.0%
✅ At least 70% of repos have dependencies
   Value: 90.0% | Threshold: 70.0%
✅ Average resolution rate >= 75%
   Value: 87.5% | Threshold: 75.0%
✅ Less than 20% of repos have errors
   Value: 10.0% | Threshold: 20.0%
```

### Phase 2: Quality Gate Evaluation

**If PASSED** ✅:
- Review metrics
- Proceed to full ingestion
- No fixes needed

**If FAILED** ❌:
- Review failing criteria
- Check error messages in report
- Fix discovery/parsing issues
- Re-run pilot

**Common Issues**:

1. **Low manifest coverage** (<80%)
   - Check: Are repos missing manifest files?
   - Fix: Verify manifest discovery logic
   - Test: `ManifestDiscovery.discover_manifests(repo)`

2. **Low dependency coverage** (<70%)
   - Check: Are manifests being parsed correctly?
   - Fix: Verify parser registry handles all formats
   - Test: `DependencyParserRegistry.parse_file(path, content)`

3. **Low resolution rate** (<75%)
   - Check: Are PyPI/npm APIs responding?
   - Fix: Verify package resolver logic
   - Test: `PackageResolver.resolve(package, registry)`

4. **High error rate** (>20%)
   - Check: Review error messages in report
   - Fix: Address specific errors
   - Test: Re-run failing repos individually

### Phase 3: Full Ingestion (50 repos)

**Command** (only after pilot passes):
```bash
./scripts/ingest_dataset.sh full
```

**What it does**:
1. Ingests all 50 repos from `data/repos_full.txt`
2. Same process as pilot (discover, parse, resolve)
3. Generates comprehensive dataset report
4. Evaluates quality gate

**Expected Duration**: 45-60 minutes

**Expected Output**:
```
INGESTION SUMMARY
Total repos: 50
Successful: 45-48
Total dependencies: 1000-2000
Total resolved: 850-1700 (85-90%)

QUALITY GATE
Status: ✅ PASSED
```

---

## 📊 Quality Gate Criteria

### Criterion 1: Manifest Coverage
- **Threshold**: ≥80% of repos have manifests
- **Measures**: Discovery effectiveness
- **Failure indicates**: Manifest discovery issues

### Criterion 2: Dependency Coverage
- **Threshold**: ≥70% of repos have dependencies
- **Measures**: Parsing effectiveness
- **Failure indicates**: Parser issues

### Criterion 3: Resolution Rate
- **Threshold**: ≥75% average resolution rate
- **Measures**: Package → GitHub mapping success
- **Failure indicates**: Resolver issues or API problems

### Criterion 4: Error Rate
- **Threshold**: ≤20% of repos have errors
- **Measures**: Overall ingestion health
- **Failure indicates**: Systematic issues

---

## 📈 Dataset Report Format

### Summary Statistics
```
Total repos:              50
Repos with manifests:     48 (96.0%)
Repos with dependencies:  46 (92.0%)
Total manifests:          85
Total dependencies:       1500
Total resolved:           1350 (90.0%)
Total CVEs:               120
Repos with errors:        2 (4.0%)

Manifest Type Distribution:
  requirements.txt      35
  package.json          28
  pyproject.toml        15
  pom.xml               5
  go.mod                2
```

### Per-Repo Metrics
```
Repository                          Mnfst  Deps   Rslvd  Rate   CVEs   Errs
--------------------------------------------------------------------------------
   pallets/flask                    2      39     36     92.3%  3      0
   django/django                    3      52     48     92.3%  8      0
   psf/requests                     1      25     23     92.0%  5      0
⚠️  some/repo                        0      0      0      0.0%   0      1
      └─ No manifests found
```

---

## 🔧 Troubleshooting

### Issue: Pilot fails quality gate

**Step 1**: Review the dataset report
```bash
python scripts/generate_dataset_report.py
```

**Step 2**: Identify failing criteria
- Look for ❌ marks in quality gate section
- Read the recommendation

**Step 3**: Check specific repos with errors
- Look for ⚠️ marks in per-repo metrics
- Read error messages

**Step 4**: Test individual repos
```python
from src.open_source_risk_model.dependencies.ingestion_service import DependencyIngestionService

service = DependencyIngestionService('data/graphs.db')
result = service.ingest_repo('owner/repo', refresh=True)

print(f"Manifests: {result.manifests_discovered}")
print(f"Dependencies: {result.dependencies_found}")
print(f"Errors: {result.errors}")
```

**Step 5**: Fix and re-run pilot
```bash
./scripts/ingest_dataset.sh pilot
```

### Issue: GitHub rate limit exceeded

**Solution**: Set GITHUB_TOKEN in `.env`
```bash
echo "GITHUB_TOKEN=ghp_your_token_here" >> .env
```

### Issue: Slow ingestion

**Expected**: 10-15 minutes for pilot, 45-60 minutes for full
**If slower**: Check network connection, API rate limits

### Issue: Parser errors

**Check**: Which manifest types are failing
```bash
python scripts/generate_dataset_report.py | grep "error"
```

**Fix**: Update parser for specific manifest type

---

## 📁 Repository Selection Strategy

### Pilot Repos (10)
**Optimized for**: High dependency overlap, diverse manifest types

**Python** (5):
- requests/requests - HTTP library (high overlap)
- pallets/flask - Web framework (high overlap)
- psf/requests - HTTP library (high overlap)
- django/django - Web framework (high overlap)
- pytest-dev/pytest - Testing framework (high overlap)

**JavaScript** (5):
- expressjs/express - Backend framework (high overlap)
- lodash/lodash - Utility library (high overlap)
- axios/axios - HTTP library (high overlap)
- facebook/react - Frontend framework (high overlap)
- webpack/webpack - Build tool (high overlap)

**Why these?**:
- Many repos depend on these (high overlap)
- Multiple manifest types (requirements.txt, package.json, pyproject.toml)
- Well-maintained with good metadata
- Representative of real-world ecosystems

### Full Dataset (50)
**Optimized for**: Ecosystem coverage, dependency relationships

**Python** (28):
- Web frameworks: Flask, Django, FastAPI, Tornado
- Data science: NumPy, Pandas, Scikit-learn, Matplotlib
- Testing: Pytest, Tox, Coverage
- CLI tools: Click, Rich, Typer
- HTTP: Requests, HTTPX, AIOHTTP
- Utilities: PyYAML, Jinja2, Black, Pylint

**JavaScript** (22):
- Frontend: React, Vue, Angular, Svelte, Next.js
- Backend: Express, Koa, Fastify, NestJS
- Build tools: Webpack, Vite, Rollup, ESBuild
- Testing: Jest, Mocha, Cypress, Playwright
- Utilities: Lodash, Axios, Moment, Ramda

**Why this split?**:
- Python has more repos (28) because it has better manifest standardization
- JavaScript repos (22) often have complex dependency trees
- Total optimizes for dependency overlap, not strict 25/25 split

---

## ✅ Success Criteria

### Pilot Success
- ✅ 8-10 repos ingested successfully
- ✅ Quality gate passes
- ✅ No systematic errors
- ✅ Resolution rate ≥75%

### Full Dataset Success
- ✅ 45-50 repos ingested successfully
- ✅ Quality gate passes
- ✅ 1000-2000 dependencies stored
- ✅ 850-1700 dependencies resolved (85-90%)
- ✅ 100-200 CVEs tracked
- ✅ Multiple manifest types represented

---

## 🚀 Quick Start

### Run Pilot
```bash
# 1. Run pilot ingestion
./scripts/ingest_dataset.sh pilot

# 2. Review report (automatically generated)
# Look for "Quality gate PASSED" or "Quality gate FAILED"

# 3. If passed, proceed to full ingestion
./scripts/ingest_dataset.sh full

# 4. If failed, fix issues and re-run pilot
```

### Generate Report Manually
```bash
# Generate report for current database
python scripts/generate_dataset_report.py

# Save report to JSON
python scripts/generate_dataset_report.py --output report.json

# Get JSON output only
python scripts/generate_dataset_report.py --json-only
```

### Ingest Custom List
```bash
# Create custom repo list
echo "owner/repo1" > my_repos.txt
echo "owner/repo2" >> my_repos.txt

# Ingest custom list
./scripts/ingest_dataset.sh custom my_repos.txt
```

---

## 📅 Timeline

### Day 1: Pilot Ingestion
- Morning: Run pilot ingestion (15 minutes)
- Morning: Review dataset report (15 minutes)
- Afternoon: Fix any issues if gate fails (2-4 hours)
- End of day: Pilot passes quality gate

### Day 2: Full Ingestion
- Morning: Run full ingestion (60 minutes)
- Afternoon: Review dataset report (30 minutes)
- Afternoon: Validate data quality (30 minutes)
- End of day: Full dataset ready

### Day 3: Documentation & Handoff
- Morning: Document any issues encountered
- Morning: Update repo selection if needed
- Afternoon: Prepare for Week 2 (Intent API)

---

## 📊 Expected Metrics (Full Dataset)

### Ingestion Metrics
- **Total repos**: 50
- **Successful**: 45-48 (90-96%)
- **Failed**: 2-5 (4-10%)

### Dependency Metrics
- **Total dependencies**: 1000-2000
- **Resolved**: 850-1700 (85-90%)
- **Unresolved**: 150-300 (10-15%)

### Manifest Metrics
- **Total manifests**: 80-100
- **requirements.txt**: 30-40
- **package.json**: 25-35
- **pyproject.toml**: 15-20
- **Other**: 5-10

### CVE Metrics
- **Total CVEs**: 100-200
- **High severity**: 20-40
- **Medium severity**: 40-80
- **Low severity**: 40-80

---

## 🎯 Week 1 Completion Checklist

- [ ] Pilot ingestion completed
- [ ] Pilot quality gate passed
- [ ] Full ingestion completed
- [ ] Full quality gate passed
- [ ] Dataset report generated
- [ ] Metrics meet expectations
- [ ] No systematic errors
- [ ] Ready for Week 2 (Intent API)

---

**Once Week 1 is complete, you'll have a solid dataset foundation for building the Intelligence Layer.**

**Next**: Week 2 - Intent-Based Query API
