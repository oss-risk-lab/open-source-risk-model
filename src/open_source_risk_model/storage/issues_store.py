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
