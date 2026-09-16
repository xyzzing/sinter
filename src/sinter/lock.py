"""Exclusive file lock for SINTER supervisor operations."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator


@contextmanager
def acquire_lock(runtime_dir: Path, timeout: float = 5.0) -> Generator[Path, None, None]:
    """Acquire exclusive file lock at $XDG_RUNTIME_DIR/sinter/sinter.lock.

    Uses O_EXCL create semantics for atomicity. The lock file persists
    until the owning process releases it (context exit).

    Yields the lock path on success. Raises TimeoutError if lock is held.
    """

    runtime_dir.mkdir(parents=True, exist_ok=True)
    lock_path = runtime_dir / "sinter.lock"

    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_EXCL)
    try:
        # Write our PID for debugging
        os.write(fd, str(os.getpid()).encode())
        yield lock_path
    except Exception:
        os.unlink(lock_path)
        raise
    else:
        os.unlink(lock_path)