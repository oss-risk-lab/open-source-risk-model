# Feature Branch Workflow

## Quick Start

### Starting a New Feature

```bash
# Option 1: Use helper script
./scripts/start_feature.sh phase-c-package-resolution

# Option 2: Manual
git checkout main
git pull origin main
git checkout -b feature/phase-c-package-resolution
```

### Working on the Feature

```bash
# Make changes, then when ready:
./scripts/finish_feature.sh "feat: Add package resolution (Phase C)"

# Or manually:
git add -A
git commit -m "feat: Add package resolution (Phase C)"
git push origin feature/phase-c-package-resolution
```

### Creating a Pull Request

After pushing, you'll get a URL like:
```
https://github.com/oss-risk-lab/open-source-risk-model/compare/feature/phase-c-package-resolution?expand=1
```

Click it to create the PR, or go to GitHub and click "Compare & pull request"

---

## Workflow with Kiro

When working with me on a new feature:

### 1. Tell Me to Start a Feature Branch

**You say:** "Let's start Phase C on a feature branch"

**I'll run:**
```bash
git checkout main
git pull origin main
git checkout -b feature/dependency-graph-phase-c
```

### 2. We Build the Feature Together

I'll create files, write code, run tests, etc.

### 3. Commit and Push When Ready

**You say:** "Let's commit and push this"

**I'll run:**
```bash
git add <all-new-files>
git commit -m "feat: Add package resolution (Phase C)

- Implement PackageResolver
- Add PyPI and npm resolution
- Add RESOLVES_TO edge type
- Update GraphBuilder integration
- Add comprehensive tests"

git push origin feature/dependency-graph-phase-c
```

### 4. Create Pull Request

**I'll give you:**
- Direct link to create PR
- Pre-written PR description
- Summary of changes

**You:**
- Click the link
- Review the changes
- Click "Create Pull Request"
- Merge when ready

---

## Benefits

### For Solo Development
- ✅ Clean separation of features
- ✅ Easy to experiment without breaking main
- ✅ Can work on multiple features in parallel
- ✅ Easy rollback if something goes wrong

### For Team Development
- ✅ Code review before merging
- ✅ Discussion on specific changes
- ✅ CI/CD runs tests automatically
- ✅ Clear history of what changed when

---

## Example: Phase C Workflow

```bash
# 1. Start Phase C
./scripts/start_feature.sh phase-c-package-resolution

# 2. Work with Kiro to build Phase C
# ... Kiro creates files, writes code ...

# 3. Commit and push
./scripts/finish_feature.sh "feat: Add package resolution (Phase C)"

# 4. Create PR on GitHub
# Click the URL provided

# 5. Review and merge
# Review changes, then click "Merge pull request"

# 6. Update local main
git checkout main
git pull origin main
```

---

## Advanced: Multiple Features in Parallel

```bash
# Work on Phase C
git checkout -b feature/phase-c-package-resolution
# ... make changes ...
git push origin feature/phase-c-package-resolution

# Switch to work on documentation
git checkout main
git checkout -b feature/update-docs
# ... make changes ...
git push origin feature/update-docs

# Switch back to Phase C
git checkout feature/phase-c-package-resolution
```

---

## Troubleshooting

### Forgot to Create Branch

```bash
# If you made changes on main by accident:
git stash                    # Save your changes
git checkout -b feature/my-feature  # Create branch
git stash pop                # Restore changes
git add -A
git commit -m "your message"
git push origin feature/my-feature
```

### Want to Update Branch with Latest Main

```bash
git checkout feature/my-feature
git fetch origin
git rebase origin/main
# Or: git merge origin/main
```

### Delete a Feature Branch

```bash
# After merging PR:
git checkout main
git branch -d feature/my-feature           # Delete local
git push origin --delete feature/my-feature  # Delete remote
```

---

## GitHub CLI (Optional)

Install GitHub CLI for even faster PR creation:

```bash
# Install (macOS)
brew install gh

# Authenticate
gh auth login

# Create PR from command line
gh pr create --title "Add package resolution (Phase C)" --body "..."

# View PRs
gh pr list

# Merge PR
gh pr merge
```

---

## Next Steps

When you're ready to start Phase C, just say:

**"Let's start Phase C on a feature branch"**

And I'll:
1. Create the branch
2. Build the feature
3. Commit and push
4. Give you the PR link

Easy! 🚀
