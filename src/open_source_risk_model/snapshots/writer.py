"""
Append-only gzip JSONL writer for snapshot records.

Writes one immutable file per run:
  <output_dir>/snapshots/<year>/deep-signal-snapshot-<YYYY-MM-DD>.jsonl.gz

And one manifest:
  <output_dir>/manifests/<YYYY-MM-DD>.json

All writes are atomic: records go to a .tmp file first, then os.rename()
to the target on close(). A crash mid-write leaves a .tmp orphan; the
target is never partially overwritten.
"""

import gzip
import json
import os
from datetime import date
from pathlib import Path
from typing import IO, Optional

from .models import RunManifest, SnapshotRecord


class SnapshotWriter:
    """Streams SnapshotRecords to a dated gzip JSONL file."""

    def __init__(self, output_dir: Path, run_date: date, force: bool = False) -> None:
        self.output_dir = Path(output_dir)
        self.run_date = run_date
        self.force = force
        self._gz_handle: Optional[IO[str]] = None
        self._tmp_path: Optional[Path] = None
        self._target_path: Optional[Path] = None

    # ------------------------------------------------------------------
    # Path helpers
    # ------------------------------------------------------------------

    def snapshot_path(self) -> Path:
        year = str(self.run_date.year)
        name = f"deep-signal-snapshot-{self.run_date.isoformat()}.jsonl.gz"
        return self.output_dir / "snapshots" / year / name

    def manifest_path(self) -> Path:
        return self.output_dir / "manifests" / f"{self.run_date.isoformat()}.json"

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open the gzip temp file for writing. Raises FileExistsError if target
        exists and force=False."""
        target = self.snapshot_path()
        if target.exists() and not self.force:
            raise FileExistsError(
                f"Snapshot file already exists for {self.run_date}: {target}. "
                "Pass force=True to overwrite."
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path().parent.mkdir(parents=True, exist_ok=True)

        tmp = target.parent / (target.name + ".tmp")
        self._target_path = target
        self._tmp_path = tmp
        self._gz_handle = gzip.open(tmp, "wt", encoding="utf-8")

    def write_record(self, record: SnapshotRecord) -> None:
        """Append one JSON line to the open gzip file."""
        if self._gz_handle is None:
            raise RuntimeError("SnapshotWriter is not open; call open() first.")
        self._gz_handle.write(json.dumps(record.to_json_dict(), ensure_ascii=False) + "\n")

    def close(self, manifest: RunManifest) -> None:
        """Flush and atomically rename the temp file, then write the manifest."""
        if self._gz_handle is not None:
            self._gz_handle.close()
            self._gz_handle = None
        if self._tmp_path is not None and self._target_path is not None:
            os.rename(self._tmp_path, self._target_path)
            self._tmp_path = None
        self.manifest_path().write_text(
            json.dumps(manifest.to_json_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "SnapshotWriter":
        self.open()
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: object,
    ) -> None:
        # On exception: close the gz handle without renaming so the target
        # file is never partially overwritten. The .tmp orphan can be cleaned
        # up manually. close(manifest) must be called explicitly inside the
        # with block on the success path.
        if self._gz_handle is not None:
            self._gz_handle.close()
            self._gz_handle = None
