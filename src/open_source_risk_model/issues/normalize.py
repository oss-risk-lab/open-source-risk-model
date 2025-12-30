from __future__ import annotations

from typing import Any, Dict, Optional


MAINTAINER_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}


def is_bot_login(login: Optional[str]) -> bool:
    if not login:
        return False
    return login.endswith("[bot]")


def normalize_issue(full_name: str, issue: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a GitHub issue payload into a stable schema.

    IMPORTANT: GitHub's /issues endpoint includes PRs.
    If this payload is a PR, return {} so callers can skip it.
    """
    # PRs show up in the issues endpoint; they include a 'pull_request' field
    if "pull_request" in issue:
        return {}

    user = issue.get("user") or {}
    login = user.get("login")

    labels_raw = issue.get("labels") or []
    label_names = []
    for lab in labels_raw:
        if isinstance(lab, dict) and "name" in lab:
            label_names.append(lab["name"])
        elif isinstance(lab, str):
            # sometimes labels can appear as strings depending on source
            label_names.append(lab)

    return {
        "repo_full_name": full_name,
        "issue_id": issue.get("id"),
        "issue_number": issue.get("number"),
        "title": issue.get("title") or "",
        "body": issue.get("body") or "",
        "state": issue.get("state"),  # "open" or "closed"
        "created_at": issue.get("created_at"),
        "updated_at": issue.get("updated_at"),
        "closed_at": issue.get("closed_at"),
        "author_login": login,
        "author_is_bot": is_bot_login(login),
        "author_association": issue.get("author_association"),
        "labels": label_names,
        "comments_count": int(issue.get("comments") or 0),
        "comments_url": issue.get("comments_url"),
    }


def normalize_comment(full_name: str, issue_number: int, comment: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a GitHub issue comment payload into a stable schema.
    """
    user = comment.get("user") or {}
    login = user.get("login")

    assoc = comment.get("author_association")

    return {
        "repo_full_name": full_name,
        "issue_number": issue_number,
        "comment_id": comment.get("id"),
        "body": comment.get("body") or "",
        "created_at": comment.get("created_at"),
        "updated_at": comment.get("updated_at"),
        "author_login": login,
        "author_is_bot": is_bot_login(login),
        "author_association": assoc,
        "is_maintainer": bool(assoc in MAINTAINER_ASSOCIATIONS),
    }
