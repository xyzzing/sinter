# Sinter

[![CI](https://github.com/xyzzing/sinter/actions/workflows/ci.yml/badge.svg)](https://github.com/xyzzing/sinter/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![ROCm](https://img.shields.io/badge/ROCm-AMD-red.svg)](https://rocm.docs.amd.com/)

Auditable, reproducible local inference supervisor for AMD Radeon workstations.

Sinter manages `llama-server` processes with deterministic lifecycle control, conservative pre-flight admission checks, and verifiable state transitions. It runs directly on loopback — no in-path HTTP proxy, no magic.

## Features

- **Process supervision**: Finite state machine with explicit lifecycle transitions
- **Memory admission**: Conservative VRAM budgeting with safety reserves
- **Profile management**: TOML-based model profiles with validation
- **Hardware probing**: Read-only capability detection (`sinter doctor`)
- **Context benchmarking**: Find optimal context sizes (`sinter bench`)
- **Backend updates**: Version management and feature detection (`sinter update`)
- **Loopback isolation**: Backend binds to 127.0.0.1 by default

## Installation

```bash
# From source
git clone https://github.com/sinter-project/sinter.git
cd sinter
pip install -e .

# Or install from PyPI (when available)
pip install sinter
```

### Requirements

- Python 3.11+
- AMD Radeon GPU with ROCm drivers
- llama.cpp build with ROCm support

## Quick Start

```bash
# Check hardware capabilities
sinter doctor

# Set up your first profile (detects llama-server automatically)
sinter setup --profile coding --backend /path/to/llama-server --weights /path/to/model.gguf

# Validate the profile
sinter validate coding

# Plan resource usage
sinter plan coding

# Start the backend
sinter up coding

# Check status
sinter status

# Stop the backend
sinter down
```

## Configuration

Sinter uses TOML configuration files. Profiles live in `~/.config/sinter/profiles/`.

Use `sinter setup` to create a profile from detected software, or copy the example:

```bash
cp profiles/coding.toml.example ~/.config/sinter/profiles/coding.toml
# Edit the copied file with your actual paths
```

Example profile:

```toml
[profiles.coding]
weights_path = "/absolute/path/to/model.gguf"
backend_binary = "/absolute/path/to/llama-server"
n_gpu_layers = 0
ctx_size = 16384
cache_type_k = "q4_0"
cache_type_v = "q4_0"
flash_attn = true
threads = 6
port = 8080
```

> **Note**: `n_gpu_layers = 0` and `ctx_size = 16384` are safe placeholders. Use `sinter plan` to determine optimal values for your hardware.

See [docs/configuration.md](docs/configuration.md) for complete configuration reference.

## CLI Reference

| Command | Description |
|---------|-------------|
| `sinter doctor` | Hardware/backend capability report |
| `sinter validate <profile>` | Validate profile specification |
| `sinter plan <profile>` | Show requested vs effective settings |
| `sinter up <profile>` | Start llama-server |
| `sinter down` | Stop llama-server |
| `sinter status` | Show instance status (includes telemetry) |
| `sinter telemetry` | One-shot sensor probe |
| `sinter telemetry --session` | Last session summary |
| `sinter bench <profile>` | Benchmark performance |
| `sinter update --backend` | Update llama.cpp backend |
| `sinter exec --sandbox <cmd>` | Run command in sandbox |

All commands support `--json` for structured output.

## Observability (Sentinel)

Sinter includes **Sentinel**, a session-scoped telemetry system for monitoring temperature, power, and energy consumption during inference sessions.

```bash
# One-shot sensor probe
sinter telemetry

# Session summary with energy/cost
sinter telemetry --session

# Status includes live telemetry
sinter status
```

Sentinel provides:
- Temperature monitoring (edge, hotspot, memory)
- Power and energy measurement with quality tiers
- Optional electricity cost and CO₂e estimates
- Thermal policy with advisory warnings

See [docs/sentinel.md](docs/sentinel.md) for configuration and details.

## Architecture

Sinter follows a strict separation of concerns:

- **Supervisor**: Manages process lifecycle and state transitions
- **Admission**: Pre-flight memory and compatibility checks
- **Hardware**: Read-only system probing
- **Backend**: Version detection and feature management
- **Bench**: Performance benchmarking

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design documentation.

## Development

```bash
# Run tests
python3 -m pytest tests/ -v

# Run linting
python3 -m ruff check src/ tests/

# Run full verification
python3 .agentic/verify.py
```

## Roadmap

- [x] Process supervision with FSM
- [x] Memory admission checks
- [x] Hardware probing
- [x] Profile validation
- [x] Backend version detection
- [x] Context size benchmarking
- [ ] Multi-GPU support
- [ ] Automatic model downloads
- [ ] Web dashboard

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT — see [LICENSE](LICENSE) for details.