"""Tests for telemetry broadcast."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sinter.telemetry import (
    TelemetryBroadcaster,
    TelemetryState,
    collect_telemetry,
    update_state_atomic,
)


def test_update_state_atomic():
    """Atomic state update via temp file + rename."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "state.json"
        data = {"test": "value", "number": 42}

        update_state_atomic(data, target)

        # Verify file was written
        assert target.exists()
        with open(target, "r") as f:
            loaded = json.load(f)
        assert loaded == data


def test_update_state_atomic_no_partial_reads():
    """No partial reads during atomic update."""
    with tempfile.TemporaryDirectory() as tmpdir:
        target = Path(tmpdir) / "state.json"
        # Write initial state
        update_state_atomic({"initial": True}, target)

        # Update atomically
        update_state_atomic({"updated": True, "data": "new"}, target)

        # Should read complete updated state
        with open(target, "r") as f:
            loaded = json.load(f)
        assert loaded["updated"] is True
        assert "initial" not in loaded


def test_telemetry_state_dataclass():
    """TelemetryState dataclass fields."""
    state = TelemetryState(
        vram_available_mb=4096,
        vram_headroom_mb=1536,
        hotspot_celsius=75.0,
        pacing_active=False,
        gtt_spill_detected=False,
        timestamp=1234567890.0,
    )
    assert state.vram_available_mb == 4096
    assert state.pacing_active is False


def test_vram_headroom_calculation():
    """VRAM headroom = available - 2.5GB safety margin."""
    with patch("sinter.telemetry.probe") as mock_probe:
        mock_info = MagicMock()
        mock_info.gpu_vram_total_gb = 24.0
        mock_info.gpu_vram_used_gb = 16.0
        mock_info.gpu_temperature_celsius = None
        mock_info.cpu_temperature_celsius = None
        mock_probe.return_value = mock_info

        state = collect_telemetry()

        # Available = 8GB = 8192MB
        assert state.vram_available_mb == 8192
        # Headroom = 8192 - 2560 = 5632MB
        assert state.vram_headroom_mb == 5632


def test_pacing_active_high_temperature():
    """Pacing active when hotspot > 88°C."""
    with patch("sinter.telemetry.probe") as mock_probe, \
         patch("sinter.telemetry._read_gpu_temperature", return_value=90.0):
        mock_info = MagicMock()
        mock_info.gpu_vram_total_gb = 24.0
        mock_info.gpu_vram_used_gb = 10.0
        mock_probe.return_value = mock_info

        state = collect_telemetry()

        assert state.pacing_active is True
        assert state.hotspot_celsius == 90.0


def test_pacing_active_low_vram():
    """Pacing active when VRAM < 1.5GB."""
    with patch("sinter.telemetry.probe") as mock_probe, \
         patch("sinter.telemetry._read_gpu_temperature", return_value=None):
        mock_info = MagicMock()
        mock_info.gpu_vram_total_gb = 8.0
        mock_info.gpu_vram_used_gb = 6.6  # Only 1.4GB available
        mock_probe.return_value = mock_info

        state = collect_telemetry()

        assert state.pacing_active is True
        assert state.vram_available_mb < 1536


def test_telemetry_broadcaster_start_stop():
    """Telemetry broadcaster can start and stop."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        broadcaster = TelemetryBroadcaster(state_dir)

        broadcaster.start()
        # Give it time to write one state
        import time
        time.sleep(1.5)
        broadcaster.stop()

        # Verify state file was written
        instance_path = state_dir / "instance.json"
        assert instance_path.exists()


def test_telemetry_broadcaster_get_current_state():
    """Read current telemetry state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        state_dir = Path(tmpdir)
        broadcaster = TelemetryBroadcaster(state_dir)

        # Write initial state
        update_state_atomic(
            {"telemetry": {"test": True}, "instance": {}},
            state_dir / "instance.json",
        )

        state = broadcaster.get_current_state()
        assert state is not None
        assert state["telemetry"]["test"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
