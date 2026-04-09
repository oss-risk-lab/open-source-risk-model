# 📝 Commit Guidelines

**This repository is part of the product narrative. Commit history should reflect architectural clarity and evolution.**

---

## Conventional Commit Format (Required)

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Types

| Type | Purpose | Example |
|------|---------|---------|
| `feat` | New feature | `feat(query): add intent executor` |
| `fix` | Bug fix | `fix(schema): add resolution migration` |
| `test` | Add/update tests | `test(api): add query endpoint tests` |
| `refactor` | Code refactoring | `refactor(deps): extract tree builder` |
| `docs` | Documentation | `docs(north-star): add engineering discipline` |
| `chore` | Maintenance | `chore(gitignore): exclude database files` |
| `perf` | Performance | `perf(query): optimize dependency lookup` |
| `style` | Code style | `style(api): format with black` |
| `ci` | CI/CD changes | `ci(github): add test workflow` |

### Scopes

Common scopes in this project:

- `query` - Query/intelligence layer
- `api` - API endpoints
- `deps` - Dependency ingestion
- `schema` - Database schema
- `graph` - Graph generation
- `ui` - User interface
- `test` - Testing infrastructure
- `docs` - Documentation

### Description

- Use imperative mood ("add" not "added" or "adds")
- Don't capitalize first letter
- No period at the end
- Keep under 72 characters

---

## Commit Discipline

### Atomic Commits (Required)

Each commit should:
- ✅ Represent one logical change
- ✅ Be self-contained and reversible
- ✅ Pass all tests
- ✅ Have a clear purpose

### Good Examples

```bash
# Feature with tests
feat(query): add intent parser with LLM integration
test(query): add intent parser validation tests

# Bug fix with explanation
fix(resolver): handle missing repository URLs in PyPI metadata

Body: Some packages don't include repository URLs in their metadata.
Added fallback to homepage URL with lower confidence score.

# Refactoring
refactor(deps): extract tree builder to separate module

Body: Moved tree building logic from ingestion service to dedicated
TreeBuilder class for better separation of concerns.

# Documentation
docs(intelligence): document intent-based query architecture
```

### Bad Examples

```bash
# Too vague
fix: bug fixes

# Multiple changes
feat: add query API, update UI, fix tests

# Not atomic
wip: working on query stuff

# Poor description
update code

# Not imperative
added new feature
```

---

## What NOT to Commit

### Never Commit (Enforced by .gitignore)

- ❌ `.venv/` - Virtual environments
- ❌ `data/graphs.db` - Database files
- ❌ `__pycache__/`, `.pytest_cache/` - Cache directories
- ❌ `.env` - Environment files with secrets
- ❌ `*.pyc`, `*.pyo` - Compiled Python files
- ❌ `.DS_Store`, `Thumbs.db` - OS-specific files
- ❌ `node_modules/` - Dependencies
- ❌ `.idea/`, `.vscode/settings.json` - IDE settings
- ❌ `*.tmp`, `*.temp` - Temporary files

### Do Commit

- ✅ `.env.example` - Template without secrets
- ✅ Source code (`.py`, `.js`, `.html`, `.css`)
- ✅ Tests (`test_*.py`)
- ✅ Documentation (`.md`)
- ✅ Configuration templates
- ✅ Migration scripts
- ✅ Requirements files (`pyproject.toml`, `requirements.txt`)

---

## Commit Workflow

### Before Committing

1. **Run tests**
   ```bash
   pytest
   ```

2. **Check what's staged**
   ```bash
   git status
   git diff --staged
   ```

3. **Verify no secrets**
   ```bash
   # Check for common secret patterns
   git diff --staged | grep -i "password\|secret\|token\|key"
   ```

### Making the Commit

```bash
# Stage specific files (atomic commits)
git add src/open_source_risk_model/intelligence/intent_parser.py
git add test/test_intent_parser.py

# Commit with conventional format
git commit -m "feat(query): add intent parser with LLM integration"

# Or with body
git commit -m "feat(query): add intent parser with LLM integration

Implements natural language to structured intent conversion using
OpenAI API. Validates against action allowlist and parameter schemas."
```

### After Committing

```bash
# Verify commit message
git log -1

# If message needs fixing
git commit --amend -m "feat(query): add intent parser with LLM integration"
```

---

## Branch Strategy

### Main Branch

- Must remain stable
- All tests must pass
- No WIP commits
- Clean commit history

### Feature Branches

```bash
# Create feature branch
git checkout -b feat/intent-query-api

# Make atomic commits
git commit -m "feat(query): add intent schema"
git commit -m "feat(query): add intent parser"
git commit -m "test(query): add intent parser tests"

# Merge to main (after review)
git checkout main
git merge feat/intent-query-api
```

---

## Commit Message Templates

### Feature

```
feat(<scope>): <what you added>

[Why this feature is needed]
[How it works]
[Any breaking changes]
```

### Bug Fix

```
fix(<scope>): <what you fixed>

[What was broken]
[Root cause]
[How you fixed it]
```

### Test

```
test(<scope>): <what you tested>

[What scenarios are covered]
[Why these tests are important]
```

### Refactoring

```
refactor(<scope>): <what you refactored>

[Why refactoring was needed]
[What changed architecturally]
[No functional changes]
```

---

## Examples from This Project

### Good Commit History

```
feat(intelligence): add intent parser with LLM integration
test(intelligence): add intent parser validation tests
feat(intelligence): add intent executor with parameterized queries
test(intelligence): add intent executor integration tests
feat(api): add /api/query endpoint with intent validation
test(api): add query endpoint error handling tests
docs(intelligence): document intent-based query architecture
```

This tells a story:
1. Added intent parser
2. Tested it
3. Added intent executor
4. Tested it
5. Added API endpoint
6. Tested it
7. Documented it

### Bad Commit History

```
wip
fix stuff
more changes
final version
actually final
forgot to add tests
```

This tells no story and makes debugging/reverting difficult.

---

## Reviewing Commits

### Before Pushing

```bash
# Review last 5 commits
git log -5 --oneline

# Review commit details
git show HEAD

# Check for secrets
git log -p | grep -i "password\|secret\|token\|key"
```

### Cleaning Up History (Before Push)

```bash
# Interactive rebase to clean up last 3 commits
git rebase -i HEAD~3

# Options:
# - pick: keep commit
# - reword: change commit message
# - squash: combine with previous commit
# - drop: remove commit
```

---

## Common Scenarios

### Scenario 1: Multiple Related Changes

**Bad**:
```bash
git add .
git commit -m "feat: add query API"
```

**Good**:
```bash
# Commit 1: Core logic
git add src/open_source_risk_model/intelligence/intent_parser.py
git commit -m "feat(query): add intent parser"

# Commit 2: Tests
git add test/test_intent_parser.py
git commit -m "test(query): add intent parser tests"

# Commit 3: API endpoint
git add api/app.py
git commit -m "feat(api): add /api/query endpoint"

# Commit 4: API tests
git add test/test_query_endpoint.py
git commit -m "test(api): add query endpoint tests"
```

### Scenario 2: Bug Fix with Test

```bash
# Commit 1: Add failing test
git add test/test_resolver.py
git commit -m "test(resolver): add test for missing repository URL"

# Commit 2: Fix bug
git add src/open_source_risk_model/dependencies/package_resolver.py
git commit -m "fix(resolver): handle missing repository URLs

Some PyPI packages don't include repository URLs in metadata.
Added fallback to homepage URL with confidence score of 0.75."
```

### Scenario 3: Refactoring

```bash
git add src/open_source_risk_model/intelligence/tree_builder.py
git add src/open_source_risk_model/dependencies/ingestion_service.py
git commit -m "refactor(deps): extract tree builder to separate module

Moved tree building logic from ingestion service to dedicated
TreeBuilder class. No functional changes, improves separation
of concerns and testability."
```

---

## Commit Checklist

Before committing, verify:

- [ ] Commit represents one logical change
- [ ] All tests pass
- [ ] No secrets or credentials included
- [ ] No generated artifacts (`.db`, `.pyc`, etc.)
- [ ] Commit message follows conventional format
- [ ] Description is clear and imperative
- [ ] Scope is appropriate
- [ ] Body explains "why" if needed

---

## Tools

### Pre-commit Hooks (Optional)

```bash
# Install pre-commit
pip install pre-commit

# Create .pre-commit-config.yaml
cat > .pre-commit-config.yaml << EOF
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: check-added-large-files
      - id: check-yaml
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: detect-private-key
  
  - repo: https://github.com/psf/black
    rev: 23.12.1
    hooks:
      - id: black
  
  - repo: https://github.com/compilerla/conventional-pre-commit
    rev: v3.0.0
    hooks:
      - id: conventional-pre-commit
        stages: [commit-msg]
EOF

# Install hooks
pre-commit install
pre-commit install --hook-type commit-msg
```

### Commit Message Linter

```bash
# Install commitlint (requires Node.js)
npm install -g @commitlint/cli @commitlint/config-conventional

# Create commitlint.config.js
cat > commitlint.config.js << EOF
module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'scope-enum': [2, 'always', [
      'query', 'api', 'deps', 'schema', 'graph',
      'ui', 'test', 'docs', 'ci', 'chore'
    ]]
  }
};
EOF
```

---

## Resources

- [Conventional Commits](https://www.conventionalcommits.org/)
- [How to Write a Git Commit Message](https://chris.beams.io/posts/git-commit/)
- [Atomic Commits](https://www.freshconsulting.com/insights/blog/atomic-commits/)

---

**Remember: Your commit history is documentation. Make it tell a clear story.**
