"""Crucible — process supervisor with state machine."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from sinter.config import ProfileSpec


@dataclass
class InstanceRecord:
    """Record of a launched backend instance."""
    instance_uuid: str = field(default_factory=lambda: str(uuid.uuid4()))
    pid: Optional[int] = None
    start_time: Optional[int] = None  # from /proc/[pid]/stat
    port: int = 8080
    profile: str = ""
    state: str = "STOPPED"  # STOPPED, VALIDATING, STARTING, READY, STOPPING, FAILED, DEGRADED
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "instance_uuid": self.instance_uuid,
            "pid": self.pid,
            "start_time": self.start_time,
            "port": self.port,
            "profile": self.profile,
            "state": self.state,
            "created_at": self.created_at,
            "last_error": self.last_error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InstanceRecord":
        return cls(**data)


class Supervisor:
    """Manages llama-server lifecycle with state machine."""

    def __init__(self, runtime_dir: Path, state_dir: Path):
        self.runtime_dir = runtime_dir
        self.state_dir = state_dir

    def _read_proc_stat(self, pid: int) -> Optional[int]:
        """Read start_time from /proc/[pid]/stat. Returns None if process gone."""
        try:
            with open(f"/proc/{pid}/stat") as f:
                content = f.read()
            # Field 22 is start_time (ticks since boot)
            fields = content.split(" ")
            return int(fields[19])
        except (FileNotFoundError, OSError, IndexError, ValueError):
            return None

    def _verify_process(self, pid: int, expected_start_time: int) -> bool:
        """Verify a PID is still our process (not PID-wrapped)."""
        actual_start = self._read_proc_stat(pid)
        return actual_start is not None and actual_start == expected_start_time

    def _send_signal(self, pid: int, sig: int) -> bool:
        """Send signal to process. Returns False if process gone."""
        try:
            os.kill(pid, sig)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return False

    def _poll_exit(self, pid: int, timeout: float) -> bool:
        """Wait for process to exit. Returns True if exited, False if timed out."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if not self._process_exists(pid):
                return True
            time.sleep(0.1)
        return not self._process_exists(pid)

    def _process_exists(self, pid: int) -> bool:
        """Check if process exists."""
        try:
            os.kill(pid, 0)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def get_instance(self) -> Optional[InstanceRecord]:
        """Load current instance record."""
        instance_path = self.state_dir / "instance.json"
        if not instance_path.exists():
            return None
        try:
            with open(instance_path) as f:
                data = json.load(f)
            return InstanceRecord.from_dict(data)
        except (json.JSONDecodeError, KeyError):
            return None

    def save_instance(self, instance: InstanceRecord) -> None:
        """Save instance record."""
        import tempfile

        self.state_dir.mkdir(parents=True, exist_ok=True)
        instance_path = self.state_dir / "instance.json"
        fd, tmp_path = tempfile.mkstemp(dir=self.state_dir, prefix=".instance.")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(instance.to_dict(), f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.rename(tmp_path, instance_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def launch(self, profile: ProfileSpec, timeout: float = 30.0) -> InstanceRecord:
        """Launch llama-server for a profile. State: STOPPED→VALIDATING→STARTING→READY."""
        # Validate first
        from sinter.config import validate_profile

        errors = validate_profile(profile)
        if errors:
            instance = InstanceRecord(profile=profile.alias)
            instance.state = "FAILED"
            instance.last_error = "; ".join(errors)
            self.save_instance(instance)
            return instance

        # Build command
        cmd = [
            str(profile.backend_binary),
            "-m", str(profile.weights_path),
            "--host", profile.host,
            "--port", str(profile.port),
            "--n-gpu-layers", str(profile.n_gpu_layers),
            "--ctx-size", str(profile.ctx_size),
            "--cache-type-k", profile.cache_type_k,
            "--cache-type-v", profile.cache_type_v,
            "--batch-size", str(profile.batch_size),
            "--ubatch-size", str(profile.ubatch_size),
            "--threads", str(profile.threads),
            "--parallel", str(profile.n_parallel),
        ]
        if profile.flash_attn:
            cmd.append("--flash-attn")
        if profile.chat_template and profile.chat_template.exists():
            cmd.extend(["--chat-template", str(profile.chat_template)])

        # Check port conflict
        import socket

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((profile.host, profile.port))
        except OSError as e:
            instance = InstanceRecord(profile=profile.alias)
            instance.state = "FAILED"
            instance.last_error = f"Port {profile.port} is in use: {e}"
            self.save_instance(instance)
            return instance

        # Spawn
        instance = InstanceRecord(
            profile=profile.alias,
            port=profile.port,
            state="STARTING",
        )

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            instance.pid = proc.pid
            instance.start_time = self._read_proc_stat(proc.pid)
            self.save_instance(instance)
        except OSError as e:
            instance.state = "FAILED"
            instance.last_error = f"Failed to spawn llama-server: {e}"
            self.save_instance(instance)
            return instance

        # Poll /health until ready
        import urllib.request

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                req = urllib.request.Request(f"http://{profile.host}:{profile.port}/health")
                with urllib.request.urlopen(req, timeout=2) as resp:
                    if resp.status == 200:
                        instance.state = "READY"
                        self.save_instance(instance)
                        return instance
            except Exception:
                pass

            # Check if process died
            if not self._verify_process(instance.pid, instance.start_time or 0):
                instance.state = "FAILED"
                instance.last_error = "Backend process exited before becoming ready"
                self.save_instance(instance)
                return instance

            time.sleep(0.5)

        instance.state = "FAILED"
        instance.last_error = f"Backend did not become ready within {timeout}s"
        self.save_instance(instance)
        return instance

    def stop(self, timeout: float = 10.0, kill_timeout: float = 5.0) -> InstanceRecord:
        """Stop the backend. State: READY/STARTING→STOPPING→STOPPED/DEGRADED."""
        instance = self.get_instance()
        if not instance or instance.state == "STOPPED":
            return instance or InstanceRecord(state="STOPPED")

        if not instance.pid:
            instance.state = "STOPPED"
            self.save_instance(instance)
            return instance

        instance.state = "STOPPING"
        self.save_instance(instance)

        # Verify process is still ours
        if not self._verify_process(instance.pid, instance.start_time or 0):
            # Process already gone
            instance.state = "STOPPED"
            self.save_instance(instance)
            return instance

        # SIGTERM
        self._send_signal(instance.pid, signal.SIGTERM)
        if self._poll_exit(instance.pid, timeout):
            instance.state = "STOPPED"
            self.save_instance(instance)
            return instance

        # SIGKILL
        self._send_signal(instance.pid, signal.SIGKILL)
        if self._poll_exit(instance.pid, kill_timeout):
            instance.state = "STOPPED"
            self.save_instance(instance)
            return instance

        # Process still alive — degraded
        instance.state = "DEGRADED"
        instance.last_error = "Backend process did not exit after SIGKILL"
        self.save_instance(instance)
        return instance

    def status(self) -> InstanceRecord:
        """Get current instance status."""
        instance = self.get_instance()
        if not instance:
            return InstanceRecord(state="STOPPED")

        # If marked READY/STARTING but process gone, transition to STOPPED
        if instance.state in ("READY", "STARTING") and instance.pid:
            if not self._verify_process(instance.pid, instance.start_time or 0):
                instance.state = "STOPPED"
                self.save_instance(instance)

        return instance