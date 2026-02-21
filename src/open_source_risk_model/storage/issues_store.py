from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable


@dataclass(frozen=True)
class RepoIssuePaths:
    repo_dir: Path
    issues_jsonl: Path
    comments_jsonl: Path
    manifest_json: Path


class IssueStore:
    """
    Normalized storage for GitHub issues and comments.

    Layout:
      data/issues/{owner__repo}/
        issues.jsonl
        comments.jsonl
        manifest.json
    """

    def __init__(self, root_dir: str = "data/issues") -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _safe_repo_name(self, full_name: str) -> str:
        # e.g. "numpy/numpy" -> "numpy__numpy"
        return full_name.replace("/", "__")

    def _paths(self, full_name: str) -> RepoIssuePaths:
        repo_dir = self.root_dir / self._safe_repo_name(full_name)
        repo_dir.mkdir(parents=True, exist_ok=True)

        return RepoIssuePaths(
            repo_dir=repo_dir,
            issues_jsonl=repo_dir / "issues.jsonl",
            comments_jsonl=repo_dir / "comments.jsonl",
            manifest_json=repo_dir / "manifest.json",
        )

    # ---------------------------
    # Manifest helpers
    # ---------------------------

    def load_manifest(self, full_name: str) -> Dict[str, Any]:
        paths = self._paths(full_name)
        if not paths.manifest_json.exists():
            return {}
        return json.loads(paths.manifest_json.read_text())

    def save_manifest(self, full_name: str, manifest: Dict[str, Any]) -> None:
        paths = self._paths(full_name)
        payload = dict(manifest)
        payload["updated_at_utc"] = datetime.now(timezone.utc).isoformat()

        paths.manifest_json.write_text(
            json.dumps(payload, indent=2, sort_keys=True)
        )

    # ---------------------------
    # Append-only writers
    # ---------------------------

    def append_issues(
        self,
        full_name: str,
        issues: Iterable[Dict[str, Any]],
    ) -> None:
        paths = self._paths(full_name)
        with paths.issues_jsonl.open("a", encoding="utf-8") as f:
            for issue in issues:
                f.write(json.dumps(issue, ensure_ascii=False) + "\n")

    def append_comments(
        self,
        full_name: str,
        comments: Iterable[Dict[str, Any]],
    ) -> None:
        paths = self._paths(full_name)
        with paths.comments_jsonl.open("a", encoding="utf-8") as f:
            for comment in comments:
                f.write(json.dumps(comment, ensure_ascii=False) + "\n")

    # ---------------------------
    # Compaction / de-dupe
    # ---------------------------

    def compact_repo(self, full_name: str) -> Dict[str, Any]:
        """
        De-dupe issues.jsonl and comments.jsonl in-place.

        - issues de-duped by issue_id (fallback: issue_number)
        - comments de-duped by comment_id (fallback: (issue_number, created_at, author_login))

        Keeps the most recently updated record when duplicates exist.

        Returns a small stats dict suitable for logging/manifest.
        """
        paths = self._paths(full_name)

        issues_stats = self._compact_jsonl(
            paths.issues_jsonl,
            primary_key="issue_id",
            fallback_keys=("issue_number",),
            updated_key="updated_at",
        )
        comments_stats = self._compact_jsonl(
            paths.comments_jsonl,
            primary_key="comment_id",
            fallback_keys=("issue_number", "created_at", "author_login"),
            updated_key="updated_at",
        )

        return {
            "issues": issues_stats,
            "comments": comments_stats,
        }

    def _compact_jsonl(
        self,
        path: Path,
        *,
        primary_key: str,
        fallback_keys: tuple[str, ...],
        updated_key: str,
    ) -> Dict[str, Any]:
        if not path.exists():
            return {"rows_before": 0, "kept": 0, "dropped": 0, "path": str(path)}

        # Load all rows (tens of MB is OK for now; correctness > performance).
        rows: list[Dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    # skip corrupt lines rather than failing compaction
                    continue

        rows_before = len(rows)

        def make_key(obj: Dict[str, Any]) -> Any:
            k = obj.get(primary_key)
            if k is not None:
                return (primary_key, k)
            parts = tuple(obj.get(x) for x in fallback_keys)
            return ("fallback",) + parts

        def updated_value(obj: Dict[str, Any]) -> str:
            v = obj.get(updated_key)
            return v or ""

        best_by_key: Dict[Any, Dict[str, Any]] = {}
        for obj in rows:
            k = make_key(obj)
            prev = best_by_key.get(k)
            if prev is None or updated_value(obj) > updated_value(prev):
                best_by_key[k] = obj

        kept = len(best_by_key)
        dropped = max(0, rows_before - kept)

        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for obj in best_by_key.values():
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")

        tmp.replace(path)

        return {"rows_before": rows_before, "kept": kept, "dropped": dropped, "path": str(path)}
