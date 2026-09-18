"""SINTER command-line interface."""

from __future__ import annotations

import argparse
import json
import sys

from sinter import __version__
from sinter.config import load_config, validate_profile
from sinter.gguf import read_gguf_header
from sinter.hardware import probe
from sinter.lock import acquire_lock
from sinter.memory import check_admission
from sinter.supervisor import Supervisor


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
        result = {
            "profile": args.profile,
            "valid": False,
            "errors": ["Profile not found in configuration"],
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Error: profile '{args.profile}' not found in configuration")
            print(f"Available profiles: {', '.join(config.profiles.keys())}")
        return 1

    profile = config.profiles[args.profile]
    errors = validate_profile(profile)

    if errors:
        result = {
            "profile": args.profile,
            "valid": False,
            "errors": errors,
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Validation FAILED for profile '{args.profile}':")
            for err in errors:
                print(f"  - {err}")
        return 1
    else:
        result = {
            "profile": args.profile,
            "valid": True,
            "details": {
                "weights": str(profile.weights_path),
                "backend": str(profile.backend_binary),
                "device": profile.device,
                "context": profile.ctx_size,
                "gpu_layers": profile.n_gpu_layers,
                "port": profile.port,
            },
        }
        if args.json:
            print(json.dumps(result, indent=2))
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

    # Try llama-server API first for model info
    gguf_info = None
    if profile.weights_path.exists():
        try:
            import urllib.error
            import urllib.request

            req = urllib.request.Request(f"http://{profile.host}:{profile.port}/v1/models")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read())
                # Try data[].meta first (richer info), then models[].details
                for m in data.get("data", []):
                    meta = m.get("meta", {})
                    if meta:
                        gguf_info = type("GGUFInfo", (), {
                            "total_bytes": meta.get("size", 0),
                            "arch": "llama",
                            "params": meta.get("n_params", 0),
                            "n_layers": meta.get("n_layers", 0),
                            "n_heads": meta.get("n_heads", 0),
                            "n_kv_heads": meta.get("n_kv_heads", 0),
                            "embedding_dim": meta.get("n_embd", 0),
                            "context_length": meta.get("n_ctx", 0),
                            "errors": [],
                        })()
                        break
                if gguf_info is None:
                    for m in data.get("models", []):
                        details = m.get("details", {})
                        if details.get("format") == "gguf":
                            gguf_info = type("GGUFInfo", (), {
                                "total_bytes": details.get("size", 0),
                                "arch": details.get("family", ""),
                                "params": details.get("n_params", 0),
                                "n_layers": details.get("n_layers", 0),
                                "n_heads": details.get("n_heads", 0),
                                "n_kv_heads": details.get("n_kv_heads", 0),
                                "embedding_dim": details.get("n_embd", 0),
                                "context_length": details.get("n_ctx", 0),
                                "errors": [],
                            })()
                            break
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            # Server not running or API failed, fall back to GGUF parsing
            pass

    # Fall back to GGUF header parsing if API didn't work
    if gguf_info is None and profile.weights_path.exists():
        try:
            gguf_info = read_gguf_header(profile.weights_path)
        except Exception:
            gguf_info = None

    # Run admission check
    admission = None
    if gguf_info and not gguf_info.errors:
        admission = check_admission(profile, gguf_info)

    result = {
        "profile": profile.alias,
        "weights": {
            "path": str(profile.weights_path),
            "size_gb": round(gguf_info.total_bytes / (1024**3), 1) if gguf_info else None,
            "exists": profile.weights_path.exists(),
            "arch": gguf_info.arch if gguf_info else None,
            "params": gguf_info.params if gguf_info else None,
            "n_layers": gguf_info.n_layers if gguf_info else None,
            "context_length": gguf_info.context_length if gguf_info else None,
        },
        "backend": {
            "binary": str(profile.backend_binary),
            "exists": profile.backend_binary.exists(),
        },
        "admission": {
            "admitted": admission.admitted if admission else None,
            "reason": admission.reason if admission else None,
            "weights_gb": round(admission.weights_bytes / (1024**3), 1) if admission else None,
            "kv_cache_gb": round(admission.kv_bytes / (1024**3), 1) if admission else None,
            "compute_gb": round(admission.compute_bytes / (1024**3), 1) if admission else None,
            "reserve_gb": round(admission.reserve_bytes / (1024**3), 2) if admission else None,
            "required_gb": round(admission.required_bytes / (1024**3), 1) if admission else None,
            "available_gb": (
                round(admission.available_bytes / (1024**3), 1)
                if admission and admission.available_bytes else None
            ),
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
        print(f"  Weights: {profile.weights_path}")
        if result["weights"]["size_gb"]:
            print(f"  Weight size: {result['weights']['size_gb']} GB")
        if gguf_info:
            print(f"  Architecture: {gguf_info.arch}")
            print(f"  Parameters: {gguf_info.params}")
            print(f"  Layers: {gguf_info.n_layers}")
            print(f"  Model context: {gguf_info.context_length}")
        print(f"  Backend: {profile.backend_binary}")
        print(f"  Device: {profile.device}")
        print(f"  GPU layers: {profile.n_gpu_layers}")
        print(f"  Context: {profile.ctx_size}")
        print(f"  KV cache: {profile.cache_type_k} (K) / {profile.cache_type_v} (V)")
        print(f"  Flash attention: {profile.flash_attn}")
        print(f"  Threads: {profile.threads}")
        print(f"  Port: {profile.host}:{profile.port}")
        if result["admission"]["admitted"] is not None:
            print(f"  Admission: {'ADMITTED' if result['admission']['admitted'] else 'REJECTED'}")
            print(f"  Reason: {result['admission']['reason']}")
            print(f"  Required: {result['admission']['required_gb']} GB")
            if result["admission"]["available_gb"]:
                print(f"  Available: {result['admission']['available_gb']} GB")
        if errors:
            print("  Validation errors:")
            for err in errors:
                print(f"    - {err}")
        else:
            print("  Validation: OK")

    return 0 if not errors else 1


def cmd_up(args: argparse.Namespace) -> int:
    """Start llama-server for a profile."""
    config = load_config()
    if args.profile not in config.profiles:
        print(f"Error: profile '{args.profile}' not found")
        return 1

    profile = config.profiles[args.profile]
    runtime_dir = config.runtime_dir
    state_dir = config.state_dir

    try:
        with acquire_lock(runtime_dir):
            sup = Supervisor(runtime_dir, state_dir)
            # Check if already running
            existing = sup.status()
            if existing.state in ("READY", "STARTING"):
                print(f"Backend already {existing.state} (instance {existing.instance_uuid})")
                return 0

            print(f"Launching profile '{profile.alias}'...")
            instance = sup.launch(profile, timeout=args.timeout, foreground=args.foreground)

            if instance.state == "READY":
                print(f"Backend READY (instance {instance.instance_uuid}, PID {instance.pid})")
                print(f"  Port: {instance.port}")
                return 0
            else:
                print(f"Launch FAILED: {instance.last_error}")
                return 1
    except TimeoutError:
        print("Error: could not acquire supervisor lock (another sinter operation in progress)")
        return 1


def cmd_down(args: argparse.Namespace) -> int:
    """Stop the running llama-server."""
    config = load_config()
    runtime_dir = config.runtime_dir
    state_dir = config.state_dir

    try:
        with acquire_lock(runtime_dir):
            sup = Supervisor(runtime_dir, state_dir)
            instance = sup.stop(timeout=args.timeout)

            if instance.state == "STOPPED":
                print("Backend stopped.")
                return 0
            elif instance.state == "DEGRADED":
                print(f"WARNING: degraded stop — {instance.last_error}")
                return 1
            else:
                print(f"Backend stopped (was in state: {instance.state}).")
                return 0
    except TimeoutError:
        print("Error: could not acquire supervisor lock")
        return 1


def cmd_status(args: argparse.Namespace) -> int:
    """Show current instance status."""
    config = load_config()
    sup = Supervisor(config.runtime_dir, config.state_dir)
    instance = sup.status()

    result = instance.to_dict()

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"State: {instance.state}")
        if instance.instance_uuid:
            print(f"Instance: {instance.instance_uuid}")
        if instance.pid:
            print(f"PID: {instance.pid}")
        if instance.port:
            print(f"Port: {instance.port}")
        if instance.profile:
            print(f"Profile: {instance.profile}")
        if instance.created_at:
            print(f"Started: {instance.created_at}")
        if instance.last_error:
            print(f"Error: {instance.last_error}")

    return 0


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
    p_validate.add_argument("--json", action="store_true", help="Output as JSON")
    p_validate.set_defaults(func=cmd_validate)

    # plan
    p_plan = subparsers.add_parser("plan", help="Explain requested vs effective settings")
    p_plan.add_argument("profile", help="Profile alias to plan")
    p_plan.add_argument("--json", action="store_true", help="Output as JSON")
    p_plan.set_defaults(func=cmd_plan)

    # up
    p_up = subparsers.add_parser("up", help="Start llama-server for a profile")
    p_up.add_argument("profile", help="Profile alias to start")
    p_up.add_argument("--timeout", type=float, default=30.0, help="Readiness timeout (seconds)")
    p_up.add_argument("--foreground", "-F", action="store_true",
                      help="Run in foreground; attach backend output to terminal")
    p_up.set_defaults(func=cmd_up)

    # down
    p_down = subparsers.add_parser("down", help="Stop the running llama-server")
    p_down.add_argument(
        "--timeout", type=float, default=10.0,
        help="Graceful shutdown timeout (seconds)",
    )
    p_down.set_defaults(func=cmd_down)

    # status
    p_status = subparsers.add_parser("status", help="Show current instance status")
    p_status.add_argument("--json", action="store_true", help="Output as JSON")
    p_status.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
