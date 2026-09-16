"""SINTER command-line interface."""

from __future__ import annotations

import argparse
import json
import sys

from sinter import __version__
from sinter.config import load_config, validate_profile
from sinter.hardware import probe


def cmd_doctor(args: argparse.Namespace) -> int:
    """Read-only hardware/backend capability report."""
    info = probe()
    result = {
        "sinter_version": __version__,
        "os": info.os_release,
        "kernel": info.kernel,
        "cpu": {
            "model": info.cpu_model,
            "cores": info.cpu_cores,
            "threads": info.cpu_threads,
        },
        "ram": {
            "total_gb": round(info.ram_total_gb, 1),
            "available_gb": round(info.ram_available_gb, 1),
        },
        "gpu": {
            "name": info.gpu_name,
            "pci": info.gpu_pci,
            "vram_total_gb": round(info.gpu_vram_total_gb, 1) if info.gpu_vram_total_gb else None,
            "vram_used_gb": round(info.gpu_vram_used_gb, 1) if info.gpu_vram_used_gb else None,
        },
        "rocm": {
            "version": info.rocm_version,
        },
        "llama_server": {
            "running": info.llama_server_running,
            "port": info.llama_server_port,
            "version": info.llama_server_version,
        },
        "errors": info.errors,
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"SINTER doctor v{__version__}")
        print(f"  OS: {info.os_release}")
        print(f"  Kernel: {info.kernel}")
        print(f"  CPU: {info.cpu_model} ({info.cpu_cores} cores / {info.cpu_threads} threads)")
        print(f"  RAM: {info.ram_total_gb:.1f} GB total, {info.ram_available_gb:.1f} GB available")
        if info.gpu_name:
            print(f"  GPU: {info.gpu_name} ({info.gpu_pci})")
            if info.gpu_vram_total_gb:
                print(
                    f"  VRAM: {info.gpu_vram_used_gb:.1f} GB / {info.gpu_vram_total_gb:.1f} GB used"
                )
        else:
            print("  GPU: not detected")
        print(f"  ROCm: {info.rocm_version or 'not detected'}")
        if info.llama_server_running:
            print(f"  llama-server: running on port {info.llama_server_port}")
        else:
            print("  llama-server: not running")
        if info.llama_server_version:
            print(f"  llama-server version: {info.llama_server_version}")
        if info.errors:
            print("  Errors:")
            for err in info.errors:
                print(f"    - {err}")
        else:
            print("  Status: OK")

    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate a profile specification without loading weights."""
    config = load_config()
    if args.profile not in config.profiles:
        print(f"Error: profile '{args.profile}' not found in configuration")
        print(f"Available profiles: {', '.join(config.profiles.keys())}")
        return 1

    profile = config.profiles[args.profile]
    errors = validate_profile(profile)

    if errors:
        print(f"Validation FAILED for profile '{args.profile}':")
        for err in errors:
            print(f"  - {err}")
        return 1
    else:
        print(f"Validation PASSED for profile '{args.profile}'")
        print(f"  Weights: {profile.weights_path}")
        print(f"  Backend: {profile.backend_binary}")
        print(f"  Device: {profile.device}")
        print(f"  GPU layers: {profile.n_gpu_layers}")
        print(f"  Context: {profile.ctx_size}")
        return 0


def cmd_plan(args: argparse.Namespace) -> int:
    """Explain requested vs effective settings for a profile."""
    config = load_config()
    if args.profile not in config.profiles:
        print(f"Error: profile '{args.profile}' not found in configuration")
        print(f"Available profiles: {', '.join(config.profiles.keys())}")
        return 1

    profile = config.profiles[args.profile]
    errors = validate_profile(profile)

    # Estimate memory requirements
    weights_size_gb = 0
    if profile.weights_path.exists():
        weights_size_gb = profile.weights_path.stat().st_size / (1024**3)

    # Rough KV cache estimate
    # M_KV ≈ N_seq × sum over layers [C_l × (H_K × D_K + H_V × D_V)]
    # For a 27B model with ctx=131072, this is substantial
    kv_estimate_gb = (profile.ctx_size * 2 * 5120 * 4) / (1024**3)  # rough

    result = {
        "profile": profile.alias,
        "weights": {
            "path": str(profile.weights_path),
            "size_gb": round(weights_size_gb, 1) if weights_size_gb else None,
            "exists": profile.weights_path.exists(),
        },
        "backend": {
            "binary": str(profile.backend_binary),
            "exists": profile.backend_binary.exists(),
        },
        "requested": {
            "device": profile.device,
            "n_gpu_layers": profile.n_gpu_layers,
            "ctx_size": profile.ctx_size,
            "cache_type_k": profile.cache_type_k,
            "cache_type_v": profile.cache_type_v,
            "flash_attn": profile.flash_attn,
            "threads": profile.threads,
            "port": profile.port,
            "host": profile.host,
        },
        "memory_estimate": {
            "weights_gb": round(weights_size_gb, 1),
            "kv_cache_gb": round(kv_estimate_gb, 1),
            "reserve_gb": round(profile.reserve_bytes / (1024**3), 2),
            "total_estimated_gb": round(
                weights_size_gb + kv_estimate_gb + profile.reserve_bytes / (1024**3), 1
            ),
        },
        "validation_errors": errors,
        "supported": {
            "device": "unknown",
            "flash_attn": "unknown",
            "speculative_decoding": "unknown",
        },
        "unsupported": [],
        "unknown": ["device_capability", "flash_attn_support", "speculative_decoding"],
    }

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Plan for profile '{profile.alias}':")
        print(f"  Weights: {profile.weights_path} ({result['memory_estimate']['weights_gb']} GB)")
        print(f"  Backend: {profile.backend_binary}")
        print(f"  Device: {profile.device}")
        print(f"  GPU layers: {profile.n_gpu_layers}")
        print(f"  Context: {profile.ctx_size}")
        print(f"  KV cache: {profile.cache_type_k} (K) / {profile.cache_type_v} (V)")
        print(f"  Flash attention: {profile.flash_attn}")
        print(f"  Threads: {profile.threads}")
        print(f"  Port: {profile.host}:{profile.port}")
        print(f"  Memory estimate: {result['memory_estimate']['total_estimated_gb']} GB")
        if errors:
            print("  Validation errors:")
            for err in errors:
                print(f"    - {err}")
        else:
            print("  Validation: OK")

    return 0 if not errors else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sinter",
        description="SINTER — local inference supervisor for AMD ROCm workstations",
    )
    parser.add_argument("--version", action="version", version=f"sinter {__version__}")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # doctor
    p_doctor = subparsers.add_parser("doctor", help="Read-only hardware/backend capability report")
    p_doctor.add_argument("--json", action="store_true", help="Output as JSON")
    p_doctor.set_defaults(func=cmd_doctor)

    # validate
    p_validate = subparsers.add_parser("validate", help="Validate a profile specification")
    p_validate.add_argument("profile", help="Profile alias to validate")
    p_validate.set_defaults(func=cmd_validate)

    # plan
    p_plan = subparsers.add_parser("plan", help="Explain requested vs effective settings")
    p_plan.add_argument("profile", help="Profile alias to plan")
    p_plan.add_argument("--json", action="store_true", help="Output as JSON")
    p_plan.set_defaults(func=cmd_plan)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
