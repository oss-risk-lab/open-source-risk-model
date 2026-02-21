# src/open_source_risk_model/service/score_repo.py

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from open_source_risk_model.config.feature_mapping_config import get_composite_config
from open_source_risk_model.data_ingestion.github_features import fetch_repo_features
from open_source_risk_model.data_ingestion.github_issues import fetch_issues_updated_since
from open_source_risk_model.issues.metrics import compute_issue_metrics
from open_source_risk_model.score import compute_feature_risks, _weighted_composite
from open_source_risk_model.storage.issues_store import IssueStore
from open_source_risk_model.storage.snapshots import JsonSnapshotStore, RepoSnapshot
from open_source_risk_model.ui.feature_ui_metadata import DEFAULT_UI_METADATA, FEATURE_UI_METADATA

# ----------------------------
# Helpers
# ----------------------------

SNAPSHOT_SCHEMA_VERSION = "1.1"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_repo_input(repo: str) -> str:
    """
    Accepts:
      - "numpy/numpy"
      - "https://github.com/numpy/numpy"
      - "github.com/numpy/numpy"
    Returns:
      - "numpy/numpy"
    """
    repo = repo.strip()

    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if repo.startswith(prefix):
            repo = repo[len(prefix) :]

    repo = repo.strip("/")
    if repo.count("/") != 1:
        raise ValueError(f"Invalid repo identifier: {repo!r} (expected 'owner/repo')")
    return repo


def _risk_label_from_score(score: float | None) -> str | None:
    if score is None:
        return None
    if score < 0.30:
        return "low"
    if score < 0.60:
        return "medium"
    return "high"


def _snapshot_meta_from_features(features: dict[str, Any]) -> dict[str, Any]:
    """Normalize snapshot metadata access across legacy/new formats."""
    meta = features.get("__meta__", {}) or {}
    if isinstance(meta, dict):
        return meta
    return {}


# ----------------------------
# Core: build payload from snapshot
# ----------------------------

def build_ui_payload(
    full_name: str,
    snap: RepoSnapshot,
    *,
    cache_status: str = "unknown",
) -> dict[str, Any]:
    """
    Build the UI payload from a RepoSnapshot (single source of truth for snapshot storage).

    Snapshot file contains:
      - full_name
      - fetched_at
      - features (raw values + __meta__)
      - optional features["__snapshot__"] for extra runtime metadata
    """
    features: dict[str, Any] = snap.features or {}
    meta = _snapshot_meta_from_features(features)

    feature_status: dict[str, str] = meta.get("feature_status") or {}

    # composite weights
    cfg = get_composite_config()
    maintenance_cfg = cfg.get("maintenance_composite") or cfg.get("composite", {})
    feature_weights: dict[str, float] = maintenance_cfg.get("feature_weights", {})

    # compute risks + composite
    feature_risks = compute_feature_risks(features)
    composite = _weighted_composite(feature_risks, feature_weights, raw=features)

    # IMPORTANT: coverage/confidence must come from the same composite math
    coverage = float(composite.get("weighted_coverage", 0.0) or 0.0)
    confidence = composite.get("confidence", "unknown") or "unknown"

    # features payload
    items: list[dict[str, Any]] = []
    for key, weight in feature_weights.items():
        ui = FEATURE_UI_METADATA.get(key, DEFAULT_UI_METADATA)

        raw_value = features.get(key)
        status = feature_status.get(key, "ok")

        # if value missing but not explicitly not_applicable/forbidden/etc, mark missing
        if raw_value is None and status == "ok":
            status = "missing"

        risk_score = feature_risks.get(key)

        # UI contribution should align with composite logic:
        # - skip zero weights
        # - skip not_applicable/disabled
        contribution = None
        if weight is not None and float(weight) > 0.0 and status not in ("not_applicable", "disabled"):
            if risk_score is not None:
                contribution = float(risk_score) * float(weight)

        items.append(
            {
                "key": key,
                "label": key.replace("_", " ").title(),
                "category": ui.get("category"),
                "raw_value": raw_value,
                "unit": ui.get("unit"),
                "status": status,
                "risk_score": risk_score,
                "risk_label": _risk_label_from_score(risk_score),
                "weight": weight,
                "contribution": contribution,
                "explanation": ui.get("explanation"),
                "interpretation": ui.get("interpretation"),
            }
        )

    items.sort(key=lambda x: (x["contribution"] is None, -(x["contribution"] or 0.0)))

    top_drivers = [
        {"key": f["key"], "contribution": f["contribution"]}
        for f in items
        if f["contribution"] is not None
    ][:5]

    snapshot_meta = features.get("__snapshot__", {}) if isinstance(features.get("__snapshot__"), dict) else {}

    return {
        "repo": {"full_name": full_name, "url": f"https://github.com/{full_name}"},
        "meta": {
            "fetched_at": snap.fetched_at.astimezone(timezone.utc).isoformat(),
            "cache_status": cache_status,
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "issues_meta": (
                {
                    "fetch_performed": (cache_status != "hit"),
                    "last_refresh": snapshot_meta.get("issues_meta"),
                }
                if snapshot_meta.get("issues_meta") is not None
                else None
            ),

        },
        "overall": {
            "maintenance_risk": composite["overall_risk"],
            "maintenance_label": _risk_label_from_score(composite["overall_risk"]),
            "coverage": coverage,
            "confidence": confidence,
        },
        "top_drivers": top_drivers,
        "features": items,
    }


# ----------------------------
# Public API: fetch + cache + build payload
# ----------------------------

def score_repo(repo: str, *, refresh: bool = False, fetch_issues: bool = True) -> dict[str, Any]:
    """
    refresh=False:
      - use snapshot if present
      - otherwise fetch GitHub + write snapshot

    refresh=True:
      - always fetch GitHub + write snapshot

    fetch_issues=True:
      - attempts to sync issues and compute issue metrics
      - if GITHUB_TOKEN missing or fetch fails, issue metrics remain missing
    """
    full_name = _normalize_repo_input(repo)

    store = JsonSnapshotStore("data/raw_snapshots")

    if not refresh:
        cached = store.get_latest(full_name)
        if cached is not None:
            return build_ui_payload(full_name, cached, cache_status="hit")

    # 1) Fetch core repo features (can work without token, but token recommended)
    rf = fetch_repo_features(full_name)
    raw_features = rf.as_raw_dict()  # includes "__meta__"

    # Normalize naming so UI feature keys match model keys
    if raw_features.get("stars_count") is None and raw_features.get("stargazers_count") is not None:
        raw_features["stars_count"] = raw_features["stargazers_count"]

    # 2) Optionally fetch issues + compute issue metrics
    issue_meta: dict[str, Any] = {}
    if fetch_issues:
        try:
            issue_store = IssueStore(root_dir="data/issues")
            issue_meta = fetch_issues_updated_since(full_name, issue_store, days_back=365)

            repo_dir = str(Path("data/issues") / full_name.replace("/", "__"))
            issue_metrics = compute_issue_metrics(repo_dir, window_days=365)

            # merge computed issue metrics into features
            for k, v in issue_metrics.items():
                raw_features[k] = v

            # also mark their statuses as ok when present
            raw_meta = raw_features.get("__meta__", {}) or {}
            fs = raw_meta.get("feature_status", {}) or {}
            for k in issue_metrics.keys():
                fs[k] = "ok"
            raw_meta["feature_status"] = fs
            raw_features["__meta__"] = raw_meta

        except Exception as e:
            # Keep going; issue metrics just remain missing.
            issue_meta = {"error": str(e), "status": "error"}

    # store auxiliary snapshot-only metadata inside the features payload
    raw_features["__snapshot__"] = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "issues_meta": issue_meta,
    }

    snap = RepoSnapshot(
        full_name=full_name,
        fetched_at=_now_utc(),
        features=raw_features,
    )
    store.save(snap)

    return build_ui_payload(full_name, snap, cache_status=("refresh" if refresh else "miss"))
