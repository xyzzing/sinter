"""Regression tests for adversarial review findings."""

from __future__ import annotations

import json
import os
import struct
import tempfile
import threading
from pathlib import Path

from sinter.config import ProfileSpec, validate_profile
from sinter.gguf import read_gguf_header
from sinter.logging import OperationalLogger
from sinter.memory import estimate_kv_bytes


def test_supervisor_signal_permission_error():
    """PID wrap/reuse should be detected via PermissionError."""
    from sinter.supervisor import Supervisor

    with tempfile.TemporaryDirectory() as tmpdir:
        log = OperationalLogger(Path(tmpdir) / "sinter.log")
        try:
            sup = Supervisor(Path(tmpdir), log)
            # Send signal to PID 1 (init) — owned by root, should fail
            result = sup._send_signal(1, 15)
            assert result is False, "Signal to PID 1 should fail with PermissionError"
        finally:
            log.close()


def test_supervisor_start_time_none():
    """Instance with start_time=None should be treated as dead."""
    from sinter.supervisor import Supervisor, InstanceRecord

    with tempfile.TemporaryDirectory() as tmpdir:
        log = OperationalLogger(Path(tmpdir) / "sinter.log")
        try:
            sup = Supervisor(Path(tmpdir), log)
            instance = InstanceRecord(
                profile="test",
                weights_path="/fake/model.gguf",
                host="127.0.0.1",
                port=8080,
                pid=99999,  # Non-existent PID
                start_time=None,  # No start time recorded
                state="READY",
            )
            sup.save_instance(instance)
            status = sup.status()
            assert status.state == "STOPPED", "Instance with no start_time should be STOPPED"
        finally:
            log.close()


def test_memory_head_dim_validation():
    """embedding_dim not divisible by n_heads should warn."""
    # Create a mock GGUFInfo with non-divisible dimensions
    class MockGGUFInfo:
        def __init__(self):
            self.embedding_dim = 100
            self.n_heads = 7
            self.n_layers = 1
            self.n_kv_heads = 1
            self.context_length = 100
            self.params = 1000

    info = MockGGUFInfo()

    with tempfile.TemporaryDirectory() as tmpdir:
        log = OperationalLogger(Path(tmpdir) / "sinter.log")
        try:
            # Should not crash, just warn
            kv_bytes = estimate_kv_bytes(info, 100, "f16", log)
            assert kv_bytes > 0
        finally:
            log.close()


def test_gguf_corrupt_kv_recovery():
    """GGUF parser should recover from corrupt KV pairs."""
    with tempfile.NamedTemporaryFile(suffix=".gguf", delete=False) as f:
        path = f.name
        # Write valid header
        f.write(struct.pack("<I", 0x46554747))  # magic
        f.write(struct.pack("<I", 3))  # version
        f.write(struct.pack("<Q", 2))  # tensor_count
        f.write(struct.pack("<Q", 3))  # kv_count
        # First KV: valid
        f.write(struct.pack("<I", 4))  # key length
        f.write(b"arch")
        f.write(struct.pack("<I", 1))  # string type
        f.write(struct.pack("<I", 5))  # value length
        f.write(b"llama")
        # Second KV: corrupt (truncated)
        f.write(struct.pack("<I", 4))  # key length
        f.write(b"test")
        # Missing type and value — corrupt
        # Third KV: valid
        f.write(struct.pack("<I", 4))  # key length
        f.write(b"test")
        f.write(struct.pack("<I", 1))  # string type
        f.write(struct.pack("<I", 5))  # value length
        f.write(b"llama")

    info = read_gguf_header(path)
    assert info is not None
    assert info.arch == "llama"
    assert len(info.errors) >= 1, "Should have recorded error for corrupt KV pair"
    os.unlink(path)


def test_config_host_validation():
    """Profile host should be validated as loopback."""
    profile = ProfileSpec(
        name="test",
        weights_path="/fake/model.gguf",
        backend_path="/fake/llama-server",
        host="8.8.8.8",  # Public IP — should fail validation
        port=8080,
    )
    errors = validate_profile(profile)
    assert any("loopback" in e or "resolves" in e for e in errors), \
        f"Should validate host is loopback, got: {errors}"


def test_config_host_valid_loopback():
    """Profile with loopback host should pass validation."""
    profile = ProfileSpec(
        name="test",
        weights_path="/fake/model.gguf",
        backend_path="/fake/llama-server",
        host="127.0.0.1",
        port=8080,
    )
    errors = validate_profile(profile)
    # May have other errors (file not found) but not host validation
    assert not any("loopback" in e for e in errors), \
        f"Loopback host should be valid, got: {errors}"


def test_state_symlink_validation():
    """State file should not be a symlink."""
    from sinter.state import load_state

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a real file
        real_file = Path(tmpdir) / "real.json"
        real_file.write_text(json.dumps({"profile": "test"}))
        # Create a symlink to it
        link = Path(tmpdir) / "state.json"
        link.symlink_to(real_file)

        try:
            load_state(link)
            assert False, "Should have raised ValueError for symlink"
        except ValueError as e:
            assert "symlink" in str(e)


def test_logging_thread_safety():
    """Logger should be thread-safe."""
    with tempfile.TemporaryDirectory() as tmpdir:
        log_path = Path(tmpdir) / "sinter.log"
        logger = OperationalLogger(log_path)
        errors = []

        def log_event(i):
            try:
                logger.log("test_event", thread=i, data=f"payload_{i}")
            except Exception as e:
                errors.append(e)

        threads = []
        for i in range(10):
            t = threading.Thread(target=log_event, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        logger.close()

        assert not errors, f"Logging errors: {errors}"

        # Verify all 10 events were written
        with open(log_path, "r") as f:
            lines = f.readlines()
        assert len(lines) == 10, f"Expected 10 log lines, got {len(lines)}"

        # Verify JSON validity of each line
        for line in lines:
            record = json.loads(line)
            assert record["event"] == "test_event"