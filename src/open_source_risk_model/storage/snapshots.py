from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Protocol


# =========================
# Data object
# =========================

@dataclass(frozen=True)
class RepoSnapshot:
    """
    Immutable snapshot of raw GitHub-derived features for a repository.
    Represents a single point-in-time capture.
    """
    full_name: str              # "owner/repo"
    fetched_at: datetime        # timezone-aware
    features: Dict[str, Any]    # raw feature values


# =========================
# Storage interface
# =========================

class SnapshotStore(Protocol):
    """
    Interface / contract for snapshot persistence.
    """

    def get_latest(self, full_name: str) -> Optional[RepoSnapshot]:
        ...

    def save(self, snapshot: RepoSnapshot) -> None:
        ...

    def is_fresh(self, snapshot: RepoSnapshot, max_age: timedelta) -> bool:
        ...


# =========================
# JSON file implementation
# =========================

class JsonSnapshotStore:
    """
    Stores one snapshot per repository as a JSON file.
    Files are overwritten on each save (latest snapshot wins).
    """

    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)

    # ---- helpers ----

    def _path_for(self, full_name: str) -> Path:
        # Convert "owner/repo" -> "owner__repo.json"
        safe_name = full_name.replace("/", "__")
        return self.root_dir / f"{safe_name}.json"

    # ---- interface methods ----

    def get_latest(self, full_name: str) -> Optional[RepoSnapshot]:
        path = self._path_for(full_name)
        if not path.exists():
            return None

        raw = json.loads(path.read_text())

        fetched_at = datetime.fromisoformat(raw["fetched_at"])
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)

        return RepoSnapshot(
            full_name=raw.get("full_name", full_name),
            fetched_at=fetched_at,
            features=raw["features"],
        )

    def save(self, snapshot: RepoSnapshot) -> None:
        path = self._path_for(snapshot.full_name)

        payload = {
            "full_name": snapshot.full_name,
            "fetched_at": snapshot.fetched_at.astimezone(timezone.utc).isoformat(),
            "features": snapshot.features,
        }

        path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    def is_fresh(self, snapshot: RepoSnapshot, max_age: timedelta) -> bool:
        now = datetime.now(timezone.utc)
        snap_time = snapshot.fetched_at.astimezone(timezone.utc)
        return (now - snap_time) <= max_age
