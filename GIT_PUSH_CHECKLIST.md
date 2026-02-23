# Git Push Checklist

## Current Status
Last commit: `05ab982 - Replace actual token with placeholder in .env.example`  
Branch: `main`  
Date: 2026-02-23

---

## Phase B: Dependency Graph - Ready to Push ✅

### New Files (Untracked - Need `git add`)

#### Core Implementation
- [ ] `src/open_source_risk_model/dependencies/__init__.py`
- [ ] `src/open_source_risk_model/dependencies/manifest_discovery.py`
- [ ] `src/open_source_risk_model/dependencies/parsers.py`
- [ ] `src/open_source_risk_model/dependencies/manifest_cache.py`
- [ ] `src/open_source_risk_model/dependencies/rate_limiter.py`
- [ ] `src/open_source_risk_model/persistence/dependency_repo.py`

#### Documentation
- [ ] `.kiro/specs/dependency-graph/requirements.md`
- [ ] `.kiro/specs/dependency-graph/design.md`
- [ ] `.kiro/specs/dependency-graph/design-improvements.md`
- [ ] `.kiro/specs/dependency-graph/PHASE_A_COMPLETE.md`
- [ ] `.kiro/specs/dependency-graph/PHASE_B_COMPLETE.md`
- [ ] `.kiro/specs/dependency-graph/SUMMARY.md`
- [ ] `.kiro/specs/deployment/aws-considerations.md`

#### Test Scripts
- [ ] `test_dependency_api.py`
- [ ] `test_phase_b_dependency_parsing.py`

#### Multi-Repo Features (from previous work)
- [ ] `WHATS_NEW_MULTI_REPO.md`
- [ ] `demo_multi_repo_features.sh`

#### GitHub Workflows (if any)
- [ ] `.github/` (check contents)

### Modified Files (Need review before commit)

#### Core Code
- [ ] `api/app.py` - Added dependency endpoints
- [ ] `src/open_source_risk_model/graph/builder.py` - Added dependency parsing integration
- [ ] `src/open_source_risk_model/graph/schema.py` - Added parse_dependencies flag
- [ ] `src/open_source_risk_model/persistence/db.py` - Schema v2 with dependency tables
- [ ] `src/open_source_risk_model/persistence/worker.py` - Bug fix (get_job call)

#### Data Files (Consider excluding from commit)
- [ ] `data/cve/PyPI__numpy.json` - Cache file
- [ ] `data/cve/PyPI__Flask.json` - Cache file
- [ ] `data/graphs/numpy__numpy__r10_m5_rf10_cves.json` - Generated graph
- [ ] `data/graphs/psf__requests__r10_m5_rf5_cves.json` - Generated graph
- [ ] `data/issues/pallets__flask/*` - Issue data
- [ ] `data/issues/psf__requests/*` - Issue data
- [ ] `data/raw_snapshots/pallets__flask.json` - Snapshot
- [ ] `data/raw_snapshots/psf__requests.json` - Snapshot
- [ ] `data/github_cache/contributors_pallets__flask.json` - Cache
- [ ] `data/github_cache/releases_pallets__flask.json` - Cache

---

## Recommended Git Workflow

### Step 1: Review Changes
```bash
# See what's changed
git status

# Review specific files
git diff api/app.py
git diff src/open_source_risk_model/graph/builder.py
git diff src/open_source_risk_model/graph/schema.py
git diff src/open_source_risk_model/persistence/db.py
```

### Step 2: Update .gitignore (if needed)
Consider adding to `.gitignore`:
```
# Cache and generated data
data/cve/*.json
data/graphs/*.json
data/issues/*/
data/raw_snapshots/*.json
data/github_cache/*.json
data/manifest_cache/
data/graphs.db
data/graphs.db-*

# Test databases
*.db
*.db-shm
*.db-wal
```

### Step 3: Stage Phase B Files
```bash
# Add new dependency parsing package
git add src/open_source_risk_model/dependencies/

# Add updated persistence layer
git add src/open_source_risk_model/persistence/dependency_repo.py
git add src/open_source_risk_model/persistence/db.py
git add src/open_source_risk_model/persistence/worker.py

# Add updated graph components
git add src/open_source_risk_model/graph/builder.py
git add src/open_source_risk_model/graph/schema.py

# Add API changes
git add api/app.py

# Add documentation
git add .kiro/specs/dependency-graph/
git add .kiro/specs/deployment/

# Add test scripts
git add test_dependency_api.py
git add test_phase_b_dependency_parsing.py

# Add multi-repo docs (if not already committed)
git add WHATS_NEW_MULTI_REPO.md
git add demo_multi_repo_features.sh
```

### Step 4: Commit Phase B
```bash
git commit -m "feat: Add dependency graph parsing (Phase B)

- Implement manifest discovery via GitHub Tree API
- Add parsers for requirements.txt, pyproject.toml, package.json
- Add manifest caching with TTL
- Add rate limit tracking and protection
- Integrate with GraphBuilder (opt-in via parse_dependencies flag)
- Update database schema to v2 with dependency tables
- Add API endpoints for querying dependencies
- Add comprehensive test suite

Phase B completes dependency parsing infrastructure.
Next: Phase C (Package Resolution)"
```

### Step 5: Push to GitHub
```bash
# Push to main branch
git push origin main

# Or create a feature branch first (recommended)
git checkout -b feature/dependency-graph-phase-b
git push origin feature/dependency-graph-phase-b
# Then create a Pull Request on GitHub
```

---

## Alternative: Feature Branch Workflow (Recommended)

### Create Feature Branch
```bash
# Create and switch to feature branch
git checkout -b feature/dependency-graph-phase-b

# Stage and commit as above
git add src/open_source_risk_model/dependencies/
git add src/open_source_risk_model/persistence/dependency_repo.py
# ... (all files from Step 3)

git commit -m "feat: Add dependency graph parsing (Phase B)"

# Push feature branch
git push origin feature/dependency-graph-phase-b
```

### Create Pull Request
1. Go to GitHub repository
2. Click "Compare & pull request"
3. Add description:
   ```
   ## Phase B: Dependency Graph Parsing
   
   This PR implements Phase B of the dependency graph feature.
   
   ### What's New
   - Manifest discovery via GitHub Tree API
   - Dependency parsers (Python, JavaScript)
   - Manifest caching and rate limiting
   - GraphBuilder integration (opt-in)
   - Database schema v2
   - API endpoints for dependencies
   
   ### Test Results
   ✅ All tests passing
   - Manifest discovery: 4/4 repos
   - Parsing: 3/3 formats
   - Database storage: Working
   - Rate limiting: Functional
   
   ### Documentation
   - `.kiro/specs/dependency-graph/PHASE_B_COMPLETE.md`
   - `.kiro/specs/dependency-graph/SUMMARY.md`
   
   ### Next Steps
   Phase C: Package Resolution
   ```
4. Request review (if working with team)
5. Merge when approved

---

## Quick Commands

### See all new files
```bash
git status --short | grep "^??"
```

### See all modified files
```bash
git status --short | grep "^ M"
```

### Stage everything except data files
```bash
git add src/
git add api/
git add .kiro/
git add test_*.py
git add *.md
```

### Unstage data files if accidentally added
```bash
git reset data/
```

### Create commit with all staged files
```bash
git commit -m "feat: Add dependency graph parsing (Phase B)"
```

---

## Checklist Summary

- [ ] Review all changes with `git diff`
- [ ] Update `.gitignore` to exclude data files
- [ ] Stage Phase B implementation files
- [ ] Stage Phase B documentation
- [ ] Stage test scripts
- [ ] Commit with descriptive message
- [ ] Push to GitHub (main or feature branch)
- [ ] Create Pull Request (if using feature branch)
- [ ] Update project board/issues

---

## Notes

### What to Commit
✅ Source code (`src/`)  
✅ API changes (`api/`)  
✅ Documentation (`.kiro/specs/`, `*.md`)  
✅ Test scripts (`test_*.py`)  
✅ Configuration examples (`.env.example`)  

### What NOT to Commit
❌ Database files (`*.db`, `*.db-*`)  
❌ Cache files (`data/cve/`, `data/github_cache/`)  
❌ Generated graphs (`data/graphs/`)  
❌ Issue data (`data/issues/`)  
❌ Snapshots (`data/raw_snapshots/`)  
❌ Manifest cache (`data/manifest_cache/`)  
❌ Environment files (`.env` with real tokens)  

### Dependencies to Document
If you added new Python packages, update:
- [ ] `pyproject.toml` (add `packaging`, `tomli`)
- [ ] `requirements.txt` (if you have one)

---

Last Updated: 2026-02-23
