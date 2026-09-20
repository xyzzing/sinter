"""Atomic telemetry broadcast (Compass).

Polls hardware at 1Hz, computes VRAM headroom and thermal state,
and writes to instance.json atomically via temp file + rename.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sinter.hardware import probe
from sinter.health import HealthMonitor


@dataclass
class TelemetryState:
    """Current telemetry state."""
    vram_available_mb: Optional[int]
    vram_headroom_mb: Optional[int]
    hotspot_celsius: Optional[float]
    pacing_active: bool
    gtt_spill_detected: bool
    timestamp: float


def update_state_atomic(state_data: dict, target_path: Path) -> None:
    """Atomically update state file via temp file + rename.

    Ensures no partial reads by other processes.
    """
    temp_path = target_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(state_data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    temp_path.replace(target_path)


def _read_gtt_spillover() -> bool:
    """Check for GTT memory spillover via sysfs.

    Returns True if GTT memory is being used (spillover detected).
    """
    # Look for AMD GPU GTT memory info
    for card_dir in Path("/sys/class/drm").glob("card*"):
        gtt_path = card_dir / "device" / "mem_info_gtt_used"
        if gtt_path.exists():
            try:
                with open(gtt_path, "r") as f:
                    content = f.read().strip()
                    # Value is in bytes
                    if content and int(content) > 0:
                        return True
            except (OSError, ValueError):
                pass
    return False


def _read_gpu_temperature() -> Optional[float]:
    """Read GPU temperature from sysfs hwmon."""
    import glob

    # Try AMD GPU temperature
    for path in glob.glob("/sys/class/hwmon/hwmon*/temp1_input"):
        try:
            with open(path, "r") as f:
                temp_millidegrees = int(f.read().strip())
                return temp_millidegrees / 1000.0
        except (OSError, ValueError):
            pass
    return None


def collect_telemetry() -> TelemetryState:
    """Collect current hardware telemetry."""
    info = probe()

    # VRAM available (in MB)
    vram_available_mb = None
    if info.gpu_vram_total_gb is not None and info.gpu_vram_used_gb is not None:
        vram_available_mb = int(
            (info.gpu_vram_total_gb - info.gpu_vram_used_gb) * 1024
        )

    # VRAM headroom: available - 2.5GB safety margin
    vram_headroom_mb = None
    if vram_available_mb is not None:
        vram_headroom_mb = vram_available_mb - 2560  # 2.5GB in MB

    # Thermal: read from sysfs hwmon
    hotspot_celsius = _read_gpu_temperature()

    # Pacing active: hotspot > 88°C or VRAM < 1.5GB
    pacing_active = False
    if hotspot_celsius is not None and hotspot_celsius > 88.0:
        pacing_active = True
    if vram_available_mb is not None and vram_available_mb < 1536:
        pacing_active = True

    # GTT spillover
    gtt_spill_detected = _read_gtt_spillover()

    return TelemetryState(
        vram_available_mb=vram_available_mb,
        vram_headroom_mb=vram_headroom_mb,
        hotspot_celsius=hotspot_celsius,
        pacing_active=pacing_active,
        gtt_spill_detected=gtt_spill_detected,
        timestamp=time.time(),
    )


class TelemetryBroadcaster:
    """Background thread that broadcasts telemetry at 1Hz."""

    def __init__(self, state_dir: Path, instance_info: Optional[dict] = None):
        self.state_dir = state_dir
        self.instance_info = instance_info or {}
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._instance_path = self.state_dir / "instance.json"
        self.health_monitor = HealthMonitor()

    def start(self) -> None:
        """Start the telemetry broadcast thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._broadcast_loop,
            daemon=True,
            name="sinter-telemetry",
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the telemetry broadcast thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _broadcast_loop(self) -> None:
        """Main broadcast loop: collect telemetry and write at 1Hz."""
        while not self._stop_event.is_set():
            try:
                telemetry = collect_telemetry()

                # Record health metrics
                health_alerts = []
                if telemetry.hotspot_celsius is not None:
                    health_alerts.extend(
                        self.health_monitor.record_temperature(
                            telemetry.hotspot_celsius
                        )
                    )

                # Calculate VRAM usage percent
                if telemetry.vram_available_mb is not None:
                    # Assume 24GB total for RX 7900 XTX
                    total_mb = 24 * 1024
                    used_mb = total_mb - telemetry.vram_available_mb
                    used_gb = used_mb / 1024.0
                    health_alerts.extend(
                        self.health_monitor.record_vram_usage(used_gb, 24.0)
                    )

                # Log alerts
                for alert in health_alerts:
                    print(f"[HEALTH {alert.severity.upper()}] {alert.message}")

                state_data = {
                    "telemetry": {
                        "vram_available_mb": telemetry.vram_available_mb,
                        "vram_headroom_mb": telemetry.vram_headroom_mb,
                        "hotspot_celsius": telemetry.hotspot_celsius,
                        "pacing_active": telemetry.pacing_active,
                        "gtt_spill_detected": telemetry.gtt_spill_detected,
                        "timestamp": telemetry.timestamp,
                    },
                    "health": self.health_monitor.get_health_summary(),
                    "instance": self.instance_info,
                }
                update_state_atomic(state_data, self._instance_path)
            except Exception:
                # Continue broadcasting even if one iteration fails
                import traceback
                traceback.print_exc()

            # Sleep for 1 second (1Hz)
            self._stop_event.wait(timeout=1.0)

    def get_current_state(self) -> Optional[dict]:
        """Read the current instance.json state."""
        try:
            with open(self._instance_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return None

    def save_health_report(self) -> Path:
        """Save a health report to file."""
        return self.health_monitor.save_health_report()
