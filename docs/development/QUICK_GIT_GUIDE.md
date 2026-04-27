# Quick Git Push Guide

## TL;DR - Push Phase B Now

```bash
# 1. Stage all Phase B files
git add src/open_source_risk_model/dependencies/
git add src/open_source_risk_model/persistence/dependency_repo.py
git add src/open_source_risk_model/persistence/db.py
git add src/open_source_risk_model/persistence/worker.py
git add src/open_source_risk_model/graph/builder.py
git add src/open_source_risk_model/graph/schema.py
git add api/app.py
git add .kiro/specs/dependency-graph/
git add .kiro/specs/deployment/
git add test_dependency_api.py
git add test_phase_b_dependency_parsing.py
git add WHATS_NEW_MULTI_REPO.md
git add demo_multi_repo_features.sh
git add pyproject.toml
git add GIT_PUSH_CHECKLIST.md
git add QUICK_GIT_GUIDE.md

# 2. Commit
git commit -m "feat: Add dependency graph parsing (Phase B)

- Implement manifest discovery via GitHub Tree API
- Add parsers for requirements.txt, pyproject.toml, package.json
- Add manifest caching with TTL
- Add rate limit tracking and protection
- Integrate with GraphBuilder (opt-in via parse_dependencies flag)
- Update database schema to v2 with dependency tables
- Add API endpoints for querying dependencies
- Add comprehensive test suite
- Add packaging and tomli dependencies

Phase B completes dependency parsing infrastructure.
Next: Phase C (Package Resolution)"

# 3. Push
git push origin main
```

---

## What You're Pushing

### New Features ✨
- Dependency graph parsing (Phase B)
- Manifest discovery across Python, JavaScript, Java, Go
- Smart caching and rate limiting
- Database schema v2 with dependency tables
- API endpoints for dependency queries

### Files Added (17 new files)
- 5 core implementation files
- 6 documentation files
- 2 test scripts
- 2 demo/guide files
- 2 tracking documents

### Files Modified (6 files)
- GraphBuilder integration
- API endpoints
- Database schema
- Worker bug fix
- Dependencies list

---

## Alternative: Feature Branch (Safer)

```bash
# Create feature branch
git checkout -b feature/dependency-graph-phase-b

# Stage and commit (same as above)
git add src/open_source_risk_model/dependencies/
# ... (all files)
git commit -m "feat: Add dependency graph parsing (Phase B)"

# Push feature branch
git push origin feature/dependency-graph-phase-b

# Then create Pull Request on GitHub
```

---

## Check Before Pushing

```bash
# See what will be committed
git status

# Review changes in key files
git diff src/open_source_risk_model/graph/builder.py
git diff api/app.py

# Make sure tests pass
python test_phase_b_dependency_parsing.py
```

---

## After Pushing

1. ✅ Verify on GitHub that all files are there
2. ✅ Check that tests would pass in CI (if you have it)
3. ✅ Update any project boards or issues
4. ✅ Consider tagging a release: `git tag v0.2.0-phase-b`

---

## Need Help?

- See full details: `GIT_PUSH_CHECKLIST.md`
- Check what's changed: `git status`
- See commit history: `git log --oneline -10`
- Undo last commit (keep changes): `git reset --soft HEAD~1`
