"""SINTER configuration schema and loading."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_CONFIG_DIR = Path.home() / ".config" / "sinter"
DEFAULT_STATE_DIR = Path.home() / ".local" / "state" / "sinter"
DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "sinter"
DEFAULT_CACHE_DIR = Path.home() / ".cache" / "sinter"


@dataclass
class ProfileSpec:
    """A single model profile specification."""
    alias: str
    weights_path: Path
    weights_digest: Optional[str] = None  # SHA-256
    backend_binary: Path = Path("/home/zacch/llama_rocmfpx_build/ROCmFPX/build/bin/llama-server")
    backend_version: Optional[str] = None
    device: str = "ROCm0"
    n_gpu_layers: int = 63
    ctx_size: int = 131072
    cache_type_k: str = "q4_0"
    cache_type_v: str = "q4_0"
    flash_attn: bool = True
    batch_size: int = 4096
    ubatch_size: int = 1024
    threads: int = 6
    n_parallel: int = 1
    port: int = 8080
    host: str = "127.0.0.1"  # loopback by default for privacy
    chat_template: Optional[Path] = None
    max_context: Optional[int] = None
    reserve_bytes: int = 512 * 1024 * 1024  # 512 MiB safety reserve


@dataclass
class SinterConfig:
    """Top-level SINTER configuration."""
    profiles: dict[str, ProfileSpec] = field(default_factory=dict)
    default_profile: str = "coding"
    config_dir: Path = DEFAULT_CONFIG_DIR
    state_dir: Path = DEFAULT_STATE_DIR
    data_dir: Path = DEFAULT_DATA_DIR
    cache_dir: Path = DEFAULT_CACHE_DIR


def load_config(config_path: Optional[Path] = None) -> SinterConfig:
    """Load configuration from TOML file.

    Resolution order:
    1. Explicit config_path argument
    2. XDG_CONFIG_HOME/sinter/config.toml
    3. ~/.config/sinter/config.toml
    """
    if config_path is None:
        xdg = os.environ.get("XDG_CONFIG_HOME")
        if xdg:
            config_path = Path(xdg) / "sinter" / "config.toml"
        else:
            config_path = DEFAULT_CONFIG_DIR / "config.toml"

    if not config_path.exists():
        return SinterConfig()

    with open(config_path, "rb") as f:
        raw = tomllib.load(f)

    config = SinterConfig()
    config.config_dir = config_path.parent

    # Parse profiles
    for alias, spec in raw.get("profiles", {}).items():
        profile = ProfileSpec(
            alias=alias,
            weights_path=Path(spec["weights_path"]),
            weights_digest=spec.get("weights_digest"),
            backend_binary=Path(spec.get("backend_binary", str(ProfileSpec.backend_binary))),
            backend_version=spec.get("backend_version"),
            device=spec.get("device", ProfileSpec.device),
            n_gpu_layers=int(spec.get("n_gpu_layers", ProfileSpec.n_gpu_layers)),
            ctx_size=int(spec.get("ctx_size", ProfileSpec.ctx_size)),
            cache_type_k=spec.get("cache_type_k", ProfileSpec.cache_type_k),
            cache_type_v=spec.get("cache_type_v", ProfileSpec.cache_type_v),
            flash_attn=bool(spec.get("flash_attn", ProfileSpec.flash_attn)),
            batch_size=int(spec.get("batch_size", ProfileSpec.batch_size)),
            ubatch_size=int(spec.get("ubatch_size", ProfileSpec.ubatch_size)),
            threads=int(spec.get("threads", ProfileSpec.threads)),
            n_parallel=int(spec.get("n_parallel", ProfileSpec.n_parallel)),
            port=int(spec.get("port", ProfileSpec.port)),
            host=spec.get("host", ProfileSpec.host),
        )
        if spec.get("chat_template"):
            profile.chat_template = Path(spec["chat_template"])
        config.profiles[alias] = profile

    config.default_profile = raw.get("default_profile", config.default_profile)
    return config


def validate_profile(profile: ProfileSpec) -> list[str]:
    """Validate a profile spec. Returns list of error strings (empty = valid)."""
    errors = []

    if not profile.alias:
        errors.append("profile alias is required")

    if not profile.weights_path.exists():
        errors.append(f"weights file not found: {profile.weights_path}")
    elif not profile.weights_path.is_file():
        errors.append(f"weights path is not a file: {profile.weights_path}")

    if not profile.backend_binary.exists():
        errors.append(f"backend binary not found: {profile.backend_binary}")

    if profile.n_gpu_layers < 0:
        errors.append(f"n_gpu_layers must be >= 0, got {profile.n_gpu_layers}")

    if profile.ctx_size <= 0:
        errors.append(f"ctx_size must be > 0, got {profile.ctx_size}")

    if profile.batch_size <= 0:
        errors.append(f"batch_size must be > 0, got {profile.batch_size}")

    if profile.threads < 1:
        errors.append(f"threads must be >= 1, got {profile.threads}")

    if profile.port < 1 or profile.port > 65535:
        errors.append(f"port must be 1-65535, got {profile.port}")

    # Validate KV cache types
    valid_cache_types = {"f16", "f32", "q4_0", "q4_1", "q5_0", "q5_1", "q8_0"}
    if profile.cache_type_k not in valid_cache_types:
        errors.append(f"invalid cache_type_k: {profile.cache_type_k}")
    if profile.cache_type_v not in valid_cache_types:
        errors.append(f"invalid cache_type_v: {profile.cache_type_v}")

    return errors
