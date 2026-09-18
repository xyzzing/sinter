"""SINTER state management with atomic writes."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Optional


@dataclass
class StateRecord:
    """Persistent state for the SINTER supervisor."""
    state: str = "STOPPED"  # STOPPED, VALIDATING, STARTING, READY, STOPPING, FAILED, DEGRADED
    backend_pid: Optional[int] = None
    backend_start_time: Optional[float] = None
    profile_alias: Optional[str] = None
    profile_hash: Optional[str] = None
    instance_id: Optional[str] = None
    last_error: Optional[str] = None


class AtomicFile:
    """Atomic file writer: writes to temp file, then renames."""

    def __init__(self, path: Path):
        self.path = path

    def write(self, data: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            os.rename(tmp_path, self.path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


def load_state(state_dir: Path) -> StateRecord:
    """Load state from disk. Returns default if not found."""
    state_path = state_dir / "state.json"
    if not state_path.exists():
        return StateRecord()
    try:
        with open(state_path) as f:
            data = json.load(f)
        # Filter to known fields to handle schema evolution gracefully
        known_fields = {f.name for f in fields(StateRecord)}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return StateRecord(**filtered)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return StateRecord()


def save_state(state_dir: Path, record: StateRecord) -> None:
    """Atomically save state to disk."""
    state_path = state_dir / "state.json"
    atomic = AtomicFile(state_path)
    atomic.write(json.dumps(asdict(record), indent=2) + "\n")