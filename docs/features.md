# Feature Definitions for Repo Health Scoring

These are the initial features we plan to extract from GitHub to evaluate repository health.

---

## 1. days_since_last_push
- **What it measures:** How recently the repository was updated.
- **How to calculate:** `current_date - repo.pushed_at` (in days).
- **Intuition:** Smaller is better (more active).

## 2. open_issues_per_1000_stars
- **What it measures:** Issue load relative to popularity.
- **How to calculate:** `repo.open_issues_count / (repo.stargazers_count / 1000)`, guarding against zero stars.
- **Intuition:** Lower is better.

## 3. fraction_issues_closed
- **What it measures:** How often issues get resolved.
- **How to calculate:** `closed_issues / total_issues` over some time window (e.g., last 12–24 months).
- **Intuition:** Higher is better.

## 4. contributors_last_12_months
- **What it measures:** Breadth of active maintainers.
- **How to calculate:** Count distinct contributors with commits in the last 12 months.
- **Intuition:** Higher is better (less single-person risk).

## 5. has_recent_release (binary)
- **What it measures:** Whether the project is shipping updates.
- **How to calculate:** `1` if there is a release in the last 12 months, else `0`.
- **Intuition:** `1` is better.

## 6. is_archived (binary)
- **What it measures:** Whether the repo is archived (no longer maintained).
- **How to calculate:** `1` if `repo.archived` is true, else `0`.
- **Intuition:** `1` is bad; we may invert this later in scoring.

## 7. bus_factor_proxy
- **What it measures:** Dependency on a single maintainer.
- **How to calculate:** `max(commits_by_single_author / total_commits)` over a recent window.
- **Intuition:** Lower is better (risk is lower when work is spread out).
