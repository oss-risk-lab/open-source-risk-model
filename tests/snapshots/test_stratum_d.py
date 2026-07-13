"""
Tests for scripts/build_stratum_d.py.

Covers: load_universe, load_candidates, build_batch_query, days_since,
fragility_score, screen_candidates (with mock GraphQL), append_to_universe.
"""

import json
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
import build_stratum_d as stratum_d


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2026, 7, 13, 12, 0, 0, tzinfo=timezone.utc)


def _make_db(tmp_path: Path, rows: list[tuple]) -> Path:
    """Create a minimal graphs.db with the given package_mappings rows."""
    db = tmp_path / "graphs.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE package_mappings "
        "(package_name TEXT, registry_type TEXT, repo_full_name TEXT, "
        "resolution_method TEXT, confidence REAL, metadata TEXT, created_at TEXT, updated_at TEXT)"
    )
    conn.executemany(
        "INSERT INTO package_mappings (package_name, registry_type, repo_full_name, confidence) VALUES (?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return db


def _make_universe(tmp_path: Path, repos: list[str], extra: list[str] | None = None) -> Path:
    path = tmp_path / "universe_v1.txt"
    lines = ["# Deep Signal Observatory -- Universe v1", ""] + repos + (extra or [])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _make_graphql_response(
    index_to_repo: dict[int, str],
    pushed_at_map: dict[str, str],       # repo -> ISO timestamp
    archived_map: dict[str, bool] | None = None,
    stars_map: dict[str, int] | None = None,
    releases_map: dict[str, int] | None = None,
    missing: set[str] | None = None,     # repos to omit from response (deleted/private)
) -> dict:
    """Build a mock GraphQL batch response."""
    archived_map = archived_map or {}
    stars_map = stars_map or {}
    releases_map = releases_map or {}
    missing = missing or set()

    data = {}
    for idx, repo in index_to_repo.items():
        alias = f"repo_{idx}"
        if repo in missing:
            data[alias] = None
            continue
        data[alias] = {
            "pushedAt": pushed_at_map.get(repo),
            "isArchived": archived_map.get(repo, False),
            "stargazerCount": stars_map.get(repo, 100),
            "releases": {"totalCount": releases_map.get(repo, 1)},
        }
    return {"data": data}


def _mock_client(responses: list[dict]) -> MagicMock:
    """Return a mock GraphQL client that yields responses in order."""
    client = MagicMock()
    client.execute_query.side_effect = responses
    return client


# ---------------------------------------------------------------------------
# load_universe
# ---------------------------------------------------------------------------


class TestLoadUniverse:
    def test_loads_repos(self, tmp_path: Path) -> None:
        path = _make_universe(tmp_path, ["owner/a", "owner/b"])
        assert stratum_d.load_universe(path) == {"owner/a", "owner/b"}

    def test_skips_comments_and_blanks(self, tmp_path: Path) -> None:
        path = _make_universe(tmp_path, ["owner/a"], extra=["# comment", "", "owner/b"])
        result = stratum_d.load_universe(path)
        assert "owner/a" in result
        assert "owner/b" in result
        assert "# comment" not in result

    def test_empty_returns_empty_set(self, tmp_path: Path) -> None:
        path = tmp_path / "u.txt"
        path.write_text("# just a comment\n\n")
        assert stratum_d.load_universe(path) == set()


# ---------------------------------------------------------------------------
# load_candidates
# ---------------------------------------------------------------------------


class TestLoadCandidates:
    def test_returns_repos_above_confidence(self, tmp_path: Path) -> None:
        db = _make_db(
            tmp_path,
            [
                ("pkg-a", "npm", "owner/a", 0.90),
                ("pkg-b", "npm", "owner/b", 0.70),  # below threshold
            ],
        )
        result = stratum_d.load_candidates(db, set(), 0.90)
        assert result == ["owner/a"]

    def test_excludes_repos_in_universe(self, tmp_path: Path) -> None:
        db = _make_db(
            tmp_path,
            [
                ("pkg-a", "npm", "owner/a", 0.90),
                ("pkg-b", "npm", "owner/b", 0.90),
            ],
        )
        result = stratum_d.load_candidates(db, {"owner/a"}, 0.90)
        assert result == ["owner/b"]

    def test_deduplicates_repos(self, tmp_path: Path) -> None:
        db = _make_db(
            tmp_path,
            [
                ("pkg-a", "npm", "owner/dup", 0.90),
                ("pkg-b", "pypi", "owner/dup", 0.95),
            ],
        )
        result = stratum_d.load_candidates(db, set(), 0.90)
        assert result.count("owner/dup") == 1

    def test_sorts_case_insensitively(self, tmp_path: Path) -> None:
        db = _make_db(
            tmp_path,
            [
                ("c", "npm", "Z/repo", 0.90),
                ("b", "npm", "a/repo", 0.90),
                ("a", "npm", "M/repo", 0.90),
            ],
        )
        result = stratum_d.load_candidates(db, set(), 0.90)
        assert result == ["a/repo", "M/repo", "Z/repo"]

    def test_skips_invalid_repo_names(self, tmp_path: Path) -> None:
        db = _make_db(
            tmp_path,
            [
                ("pkg", "npm", "not-a-valid/repo-name!", 0.90),
                ("good", "npm", "owner/valid", 0.90),
            ],
        )
        result = stratum_d.load_candidates(db, set(), 0.90)
        assert result == ["owner/valid"]


# ---------------------------------------------------------------------------
# build_batch_query
# ---------------------------------------------------------------------------


class TestBuildBatchQuery:
    def test_produces_query_and_mapping(self) -> None:
        repos = ["owner/alpha", "owner/beta"]
        query, mapping = stratum_d.build_batch_query(repos)
        assert "repo_0" in query
        assert "repo_1" in query
        assert 'owner: "owner"' in query
        assert 'name: "alpha"' in query
        assert mapping == {0: "owner/alpha", 1: "owner/beta"}

    def test_single_repo(self) -> None:
        query, mapping = stratum_d.build_batch_query(["foo/bar"])
        assert "repo_0" in query
        assert mapping == {0: "foo/bar"}
        assert "pushedAt" in query
        assert "isArchived" in query
        assert "stargazerCount" in query
        assert "releases" in query

    def test_empty_produces_minimal_query(self) -> None:
        query, mapping = stratum_d.build_batch_query([])
        assert mapping == {}
        assert "query" in query


# ---------------------------------------------------------------------------
# days_since
# ---------------------------------------------------------------------------


class TestDaysSince:
    def test_calculates_days(self) -> None:
        pushed = "2026-01-13T12:00:00Z"  # 181 days before _NOW
        result = stratum_d.days_since(pushed, _NOW)
        assert result is not None
        assert abs(result - 181) < 1

    def test_returns_none_for_none_input(self) -> None:
        assert stratum_d.days_since(None, _NOW) is None

    def test_handles_z_suffix(self) -> None:
        pushed = "2026-06-13T12:00:00Z"  # 30 days before _NOW
        result = stratum_d.days_since(pushed, _NOW)
        assert result is not None
        assert abs(result - 30) < 1

    def test_handles_offset_format(self) -> None:
        pushed = "2026-06-13T12:00:00+00:00"
        result = stratum_d.days_since(pushed, _NOW)
        assert result is not None
        assert abs(result - 30) < 1

    def test_returns_none_for_unparseable(self) -> None:
        assert stratum_d.days_since("not-a-date", _NOW) is None


# ---------------------------------------------------------------------------
# fragility_score
# ---------------------------------------------------------------------------


class TestFragilityScore:
    def test_base_score_is_days(self) -> None:
        assert stratum_d.fragility_score(200.0, 5, 500) == 200.0

    def test_no_releases_adds_90(self) -> None:
        assert stratum_d.fragility_score(200.0, 0, 500) == 290.0

    def test_low_stars_adds_30(self) -> None:
        assert stratum_d.fragility_score(200.0, 5, 10) == 230.0

    def test_combines_bonuses(self) -> None:
        assert stratum_d.fragility_score(200.0, 0, 10) == 320.0

    def test_exactly_50_stars_no_bonus(self) -> None:
        assert stratum_d.fragility_score(200.0, 5, 50) == 200.0

    def test_49_stars_gets_bonus(self) -> None:
        assert stratum_d.fragility_score(200.0, 5, 49) == 230.0


# ---------------------------------------------------------------------------
# screen_candidates
# ---------------------------------------------------------------------------


def _days_ago(n: int) -> str:
    """Return an ISO 8601 timestamp n days before _NOW."""
    from datetime import timedelta

    dt = _NOW - timedelta(days=n)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class TestScreenCandidates:
    def _run(
        self,
        repos: list[str],
        pushed_at_map: dict[str, str],
        archived_map: dict[str, bool] | None = None,
        stars_map: dict[str, int] | None = None,
        releases_map: dict[str, int] | None = None,
        missing: set[str] | None = None,
        min_stale_days: int = 180,
        cap: int = 300,
    ) -> list[tuple[str, float]]:
        _, index_to_repo = stratum_d.build_batch_query(repos)
        resp = _make_graphql_response(
            index_to_repo, pushed_at_map, archived_map, stars_map, releases_map, missing
        )
        client = _mock_client([resp])
        return stratum_d.screen_candidates(client, repos, min_stale_days, cap)

    def test_stale_repo_qualifies(self) -> None:
        repos = ["owner/stale"]
        result = self._run(repos, {"owner/stale": _days_ago(200)})
        assert [r for r, _ in result] == ["owner/stale"]

    def test_fresh_repo_excluded(self) -> None:
        repos = ["owner/fresh"]
        result = self._run(repos, {"owner/fresh": _days_ago(30)})
        assert result == []

    def test_archived_repo_excluded(self) -> None:
        repos = ["owner/archived"]
        result = self._run(
            repos,
            {"owner/archived": _days_ago(500)},
            archived_map={"owner/archived": True},
        )
        assert result == []

    def test_missing_repo_excluded(self) -> None:
        repos = ["owner/deleted"]
        result = self._run(
            repos,
            {},
            missing={"owner/deleted"},
        )
        assert result == []

    def test_mixed_universe(self) -> None:
        repos = ["owner/stale", "owner/fresh", "owner/archived", "owner/deleted"]
        result = self._run(
            repos,
            {
                "owner/stale": _days_ago(200),
                "owner/fresh": _days_ago(10),
                "owner/archived": _days_ago(400),
                "owner/deleted": _days_ago(300),
            },
            archived_map={"owner/archived": True},
            missing={"owner/deleted"},
        )
        assert [r for r, _ in result] == ["owner/stale"]

    def test_cap_limits_results(self) -> None:
        repos = [f"owner/repo{i}" for i in range(10)]
        pushed_at = {r: _days_ago(200 + i) for i, r in enumerate(repos)}
        result = self._run(repos, pushed_at, cap=3)
        assert len(result) == 3

    def test_sorted_by_score_descending(self) -> None:
        repos = ["owner/a", "owner/b", "owner/c"]
        pushed_at = {
            "owner/a": _days_ago(200),   # less stale
            "owner/b": _days_ago(500),   # most stale
            "owner/c": _days_ago(300),
        }
        result = self._run(repos, pushed_at)
        names = [r for r, _ in result]
        assert names == ["owner/b", "owner/c", "owner/a"]

    def test_no_release_bonus_in_score(self) -> None:
        repos = ["owner/noreleases", "owner/hadreleases"]
        pushed_at = {
            "owner/noreleases": _days_ago(200),
            "owner/hadreleases": _days_ago(200),
        }
        result = self._run(
            repos,
            pushed_at,
            releases_map={"owner/noreleases": 0, "owner/hadreleases": 5},
        )
        # noreleases should score higher (200 + 90 = 290) than hadreleases (200)
        names = [r for r, _ in result]
        assert names[0] == "owner/noreleases"

    def test_skips_batch_on_exception(self) -> None:
        repos = ["owner/repo"]
        client = _mock_client([Exception("network error")])
        client.execute_query.side_effect = Exception("network error")
        result = stratum_d.screen_candidates(client, repos, 180, 300)
        assert result == []

    def test_exactly_at_threshold_qualifies(self) -> None:
        repos = ["owner/exact"]
        result = self._run(repos, {"owner/exact": _days_ago(180)}, min_stale_days=180)
        assert len(result) == 1

    def test_one_day_below_threshold_excluded(self) -> None:
        repos = ["owner/close"]
        result = self._run(repos, {"owner/close": _days_ago(179)}, min_stale_days=180)
        assert result == []


# ---------------------------------------------------------------------------
# append_to_universe
# ---------------------------------------------------------------------------


class TestAppendToUniverse:
    def test_appends_repos_to_file(self, tmp_path: Path) -> None:
        universe = _make_universe(tmp_path, ["existing/repo"])
        stratum_d.append_to_universe(
            universe, ["new/repo1", "new/repo2"], date(2026, 7, 13), 180, 0.90
        )
        content = universe.read_text()
        assert "new/repo1" in content
        assert "new/repo2" in content
        assert "existing/repo" in content  # original content preserved

    def test_block_contains_date(self, tmp_path: Path) -> None:
        universe = _make_universe(tmp_path, [])
        stratum_d.append_to_universe(
            universe, ["owner/repo"], date(2026, 7, 13), 180, 0.90
        )
        content = universe.read_text()
        assert "2026-07-13" in content

    def test_block_contains_criteria(self, tmp_path: Path) -> None:
        universe = _make_universe(tmp_path, [])
        stratum_d.append_to_universe(
            universe, ["owner/repo"], date(2026, 7, 13), 270, 0.90
        )
        content = universe.read_text()
        assert "270" in content

    def test_repos_loadable_after_append(self, tmp_path: Path) -> None:
        universe = _make_universe(tmp_path, ["pre/existing"])
        stratum_d.append_to_universe(
            universe, ["new/repo"], date(2026, 7, 13), 180, 0.90
        )
        loaded = stratum_d.load_universe(universe)
        assert "pre/existing" in loaded
        assert "new/repo" in loaded

    def test_multiple_appends_accumulate(self, tmp_path: Path) -> None:
        universe = _make_universe(tmp_path, [])
        stratum_d.append_to_universe(
            universe, ["batch1/repo"], date(2026, 7, 13), 180, 0.90
        )
        stratum_d.append_to_universe(
            universe, ["batch2/repo"], date(2026, 8, 10), 180, 0.90
        )
        loaded = stratum_d.load_universe(universe)
        assert "batch1/repo" in loaded
        assert "batch2/repo" in loaded

    def test_original_repos_not_modified(self, tmp_path: Path) -> None:
        original_lines = ["# Header", "original/repo"]
        universe = tmp_path / "u.txt"
        universe.write_text("\n".join(original_lines) + "\n")
        original_content = universe.read_text()
        stratum_d.append_to_universe(
            universe, ["new/repo"], date(2026, 7, 13), 180, 0.90
        )
        new_content = universe.read_text()
        assert new_content.startswith(original_content)
