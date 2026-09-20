"""SINTER command-line interface."""

from __future__ import annotations

import argparse
import json
import sys

from sinter import __version__
from sinter.backend import detect_features, format_backend_info
from sinter.bench import bench_profile, format_bench_output
from sinter.config import load_config, validate_profile
from sinter.gguf import read_gguf_header
from sinter.hardware import probe
from sinter.lock import acquire_lock
from sinter.memory import check_admission
from sinter.sandbox import run_sandboxed
from sinter.setup import run_setup_wizard
from sinter.supervisor import Supervisor
from sinter.update import format_update_result, update_backend


def cmd_doctor(args: argparse.Namespace) -> int:
    """Read-only hardware/backend capability report."""
    info = probe()

    # Detect backend features
    config = load_config()
    backend_features = None
    if config.profiles:
        # Use the first profile's backend binary for feature detection
        first_profile = next(iter(config.profiles.values()))
        backend_features = detect_features(first_profile.backend_binary)

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
            "features": backend_features.to_dict() if backend_features else None,
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

        if backend_features:
            print()
            print(format_backend_info(backend_features))
        elif info.llama_server_version:
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

    # Check backend feature compatibility
    warnings = []
    features = detect_features(profile.backend_binary)

    if profile.flash_attn and features.flash_attn is False:
        warnings.append(
            "Profile uses flash_attn but binary doesn't support it. "
            "Run 'sinter update --backend' to improve performance."
        )

    if profile.cache_type_k not in features.cache_types and features.cache_types:
        warnings.append(
            f"Profile uses cache_type_k={profile.cache_type_k} but binary may not support it. "
            f"Supported: {', '.join(features.cache_types)}"
        )

    if profile.cache_type_v not in features.cache_types and features.cache_types:
        warnings.append(
            f"Profile uses cache_type_v={profile.cache_type_v} but binary may not support it. "
            f"Supported: {', '.join(features.cache_types)}"
        )

    if errors:
        result = {
            "profile": args.profile,
            "valid": False,
            "errors": errors,
            "warnings": warnings,
        }
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Validation FAILED for profile '{args.profile}':")
            for err in errors:
                print(f"  - {err}")
            if warnings:
                print("  Warnings:")
                for warn in warnings:
                    print(f"  - {warn}")
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
            "warnings": warnings,
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
            if warnings:
                print("  Warnings:")
                for warn in warnings:
                    print(f"  - {warn}")
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


def cmd_exec(args: argparse.Namespace) -> int:
    """Execute a command in a sandboxed environment."""
    if not args.sandbox:
        print("Error: --sandbox is required for sinter exec")
        return 1

    result = run_sandboxed(
        command=args.command,
        timeout=args.timeout,
        max_memory_mb=args.max_memory_mb,
        cpu_time_seconds=args.cpu_time_seconds,
    )

    if args.json:
        output = {
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": result.timed_out,
            "killed": result.killed,
            "elapsed_seconds": result.elapsed_seconds,
        }
        print(json.dumps(output, indent=2))
    else:
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        if result.timed_out:
            print(f"\n[timeout after {args.timeout}s]", file=sys.stderr)
        if result.killed:
            print("\n[killed]", file=sys.stderr)

    return result.exit_code


def cmd_bench(args: argparse.Namespace) -> int:
    """Benchmark a profile for performance and context size."""
    config = load_config()
    if args.profile not in config.profiles:
        print(f"Error: profile '{args.profile}' not found in configuration")
        print(f"Available profiles: {', '.join(config.profiles.keys())}")
        return 1

    profile = config.profiles[args.profile]

    # Parse context sizes if specified
    context_sizes = None
    if args.context_sizes:
        try:
            context_sizes = [int(s) for s in args.context_sizes.split(",")]
            context_sizes.sort()
        except ValueError:
            print(f"Error: invalid context sizes: {args.context_sizes}")
            return 1

    results = bench_profile(profile, context_sizes)

    if args.json:
        output = {
            "baseline": results["baseline"].to_dict(),
            "context_test": None,
        }
        if results.get("context_test"):
            ct = results["context_test"]
            output["context_test"] = {
                "max_working": ct.max_working,
                "failed_at": ct.failed_at,
                "failed_reason": ct.failed_reason,
                "tests": [t.to_dict() for t in ct.tests],
            }
        print(json.dumps(output, indent=2))
    else:
        print(format_bench_output(results))

    return 0


def cmd_update(args: argparse.Namespace) -> int:
    """Update llama.cpp backend."""
    target_version = None
    recompile = False

    if args.version:
        target_version = args.version
    if args.recompile:
        recompile = True

    result = update_backend(
        target_version=target_version,
        recompile=recompile,
        verbose=not args.json,
    )

    if args.json:
        output = {
            "success": result.success,
            "previous_version": result.previous_version,
            "new_version": result.new_version,
            "target_version": result.target_version,
            "build_time_seconds": result.build_time_seconds,
            "error": result.error,
        }
        print(json.dumps(output, indent=2))
    else:
        print(format_update_result(result))

    return 0 if result.success else 1


def cmd_setup(args: argparse.Namespace) -> int:
    """Run interactive setup wizard."""
    return run_setup_wizard()


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

    # exec
    p_exec = subparsers.add_parser("exec", help="Execute command in sandbox")
    p_exec.add_argument(
        "--sandbox", action="store_true", required=True,
        help="Run in sandboxed environment (required)",
    )
    p_exec.add_argument(
        "--timeout", type=int, default=15,
        help="Wall-clock timeout in seconds (default: 15)",
    )
    p_exec.add_argument(
        "--max-memory-mb", type=int, default=2048,
        help="Maximum virtual memory in MB (default: 2048)",
    )
    p_exec.add_argument(
        "--cpu-time-seconds", type=int, default=15,
        help="Maximum CPU time in seconds (default: 15)",
    )
    p_exec.add_argument("--json", action="store_true", help="Output as JSON")
    p_exec.add_argument("command", nargs=argparse.REMAINDER, help="Command to execute")
    p_exec.set_defaults(func=cmd_exec)

    # bench
    p_bench = subparsers.add_parser("bench", help="Benchmark a profile")
    p_bench.add_argument("profile", help="Profile alias to benchmark")
    p_bench.add_argument(
        "--context-sizes",
        help="Comma-separated list of context sizes to test (e.g. 8192,16384,32768)",
    )
    p_bench.add_argument("--json", action="store_true", help="Output as JSON")
    p_bench.set_defaults(func=cmd_bench)

    # update
    p_update = subparsers.add_parser("update", help="Update llama.cpp backend")
    p_update.add_argument(
        "--backend",
        action="store_true",
        help="Update llama.cpp backend",
    )
    p_update.add_argument(
        "version",
        nargs="?",
        help="Specific version to update to (default: latest)",
    )
    p_update.add_argument(
        "--recompile",
        action="store_true",
        help="Force recompile even if already at target version",
    )
    p_update.add_argument("--json", action="store_true", help="Output as JSON")
    p_update.set_defaults(func=cmd_update)

    # setup
    p_setup = subparsers.add_parser("setup", help="Interactive setup wizard")
    p_setup.set_defaults(func=cmd_setup)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
