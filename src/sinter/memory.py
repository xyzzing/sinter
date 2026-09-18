"""VRAM telemetry and memory admission (Anvil)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sinter.config import ProfileSpec
from sinter.gguf import GGUFInfo


@dataclass
class AdmissionResult:
    """Result of memory admission check."""
    admitted: bool
    reason: str
    weights_bytes: int = 0
    kv_bytes: int = 0
    compute_bytes: int = 0
    reserve_bytes: int = 0
    required_bytes: int = 0
    available_bytes: int = 0


def read_vram_free() -> Optional[int]:
    """Read free VRAM in bytes from sysfs.

    Uses /sys/class/drm/card*/device/mem_info_vram_* for AMD GPUs.
    Falls back to rocm-smi if sysfs is not available.
    """
    # Try sysfs first
    drm_base = Path("/sys/class/drm")
    if drm_base.exists():
        for entry in sorted(drm_base.iterdir()):
            if not entry.name.startswith("card"):
                continue
            device_dir = entry / "device"
            if not device_dir.exists():
                continue
            # Check if this is the discrete GPU (not integrated)
            try:
                with open(device_dir / "device") as f:
                    vendor_device = f.read().strip()
                # 0x1002 is AMD
                if not vendor_device.startswith("0x1002"):
                    continue
            except OSError:
                continue

            # Read VRAM info
            try:
                with open(device_dir / "mem_info_vram_total") as f:
                    total = int(f.read().strip())
                with open(device_dir / "mem_info_vram_used") as f:
                    used = int(f.read().strip())
                return total - used
            except OSError:
                continue

    # Fallback: rocm-smi
    import subprocess

    try:
        result = subprocess.run(
            ["rocm-smi", "--showmeminfo", "vram"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            total = None
            used = None
            for line in result.stdout.splitlines():
                if "VRAM Total Memory" in line:
                    try:
                        total = int(line.split(":")[-1].strip())
                    except ValueError:
                        pass
                if "VRAM Total Used Memory" in line:
                    try:
                        used = int(line.split(":")[-1].strip())
                    except ValueError:
                        pass
            if total and used:
                return total - used
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return None


def estimate_kv_bytes(
    ctx_size: int,
    n_layers: int,
    n_kv_heads: int,
    head_dim: int,
    kv_quant_bytes: float = 1.0,
) -> int:
    """Estimate KV cache size in bytes.

    M_KV = N_seq * sum over layers [C_l * (H_K * D_K + H_V * D_V) * B]
    For GQA: H_K = H_V = n_kv_heads
    Simplified: ctx * 2 * n_layers * n_kv_heads * head_dim * kv_quant_bytes
    """
    return ctx_size * 2 * n_layers * n_kv_heads * head_dim * kv_quant_bytes


def estimate_compute_bytes(ctx_size: int) -> int:
    """Rough estimate of compute buffer bytes."""
    # Activation tensors scale with context
    return ctx_size * 64 * 1024  # ~64KB per token


def check_admission(profile: ProfileSpec, gguf_info: GGUFInfo) -> AdmissionResult:
    """Check if profile can be admitted given current VRAM.

    Admission formula:
        weights + KV + compute + reserve <= available_VRAM
    """
    weights_bytes = gguf_info.total_bytes

    # Compute head dimension
    if gguf_info.embedding_dim and gguf_info.n_heads:
        if gguf_info.embedding_dim % gguf_info.n_heads != 0:
            # embedding_dim should be divisible by n_heads; warn but proceed
            import logging
            logging.getLogger(__name__).warning(
                "embedding_dim (%d) not divisible by n_heads (%d); "
                "head_dim calculation may be inaccurate",
                gguf_info.embedding_dim, gguf_info.n_heads,
            )
        head_dim = gguf_info.embedding_dim // gguf_info.n_heads
    else:
        head_dim = 128  # conservative default when architecture unknown

    # KV cache bytes
    kv_bytes = estimate_kv_bytes(
        ctx_size=profile.ctx_size,
        n_layers=gguf_info.n_layers,
        n_kv_heads=gguf_info.n_kv_heads or gguf_info.n_heads,
        head_dim=head_dim,
        kv_quant_bytes=1.0 if profile.cache_type_k in ("f16", "f32", "q8_0") else 0.5,
    )

    # Compute buffers
    compute_bytes = estimate_compute_bytes(profile.ctx_size)

    # Reserve
    reserve_bytes = profile.reserve_bytes

    required = weights_bytes + kv_bytes + compute_bytes + reserve_bytes
    available = read_vram_free()

    if available is None:
        return AdmissionResult(
            admitted=False,
            reason="Could not read available VRAM",
            weights_bytes=weights_bytes,
            kv_bytes=kv_bytes,
            compute_bytes=compute_bytes,
            reserve_bytes=reserve_bytes,
            required_bytes=required,
        )

    if required <= available:
        return AdmissionResult(
            admitted=True,
            reason="Admitted",
            weights_bytes=weights_bytes,
            kv_bytes=kv_bytes,
            compute_bytes=compute_bytes,
            reserve_bytes=reserve_bytes,
            required_bytes=required,
            available_bytes=available,
        )

    shortfall = required - available
    return AdmissionResult(
        admitted=False,
        reason=f"Insufficient VRAM: required {required / 1024**3:.1f} GB, "
               f"available {available / 1024**3:.1f} GB (shortfall {shortfall / 1024**3:.1f} GB)",
        weights_bytes=weights_bytes,
        kv_bytes=kv_bytes,
        compute_bytes=compute_bytes,
        reserve_bytes=reserve_bytes,
        required_bytes=required,
        available_bytes=available,
    )