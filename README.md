# Sinter

[![CI](https://github.com/sinter-project/sinter/actions/workflows/ci.yml/badge.svg)](https://github.com/sinter-project/sinter/actions/workflows/ci.yml)
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

# Validate a profile
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

Sinter uses TOML configuration files. Create `~/.config/sinter/config.toml`:

```toml
default_profile = "coding"

[profiles.coding]
weights_path = "/path/to/model.gguf"
backend_binary = "/path/to/llama-server"
n_gpu_layers = 63
ctx_size = 131072
cache_type_k = "q4_0"
cache_type_v = "q4_0"
flash_attn = true
threads = 6
port = 8080
```

See [docs/configuration.md](docs/configuration.md) for complete configuration reference.

## CLI Reference

| Command | Description |
|---------|-------------|
| `sinter doctor` | Hardware/backend capability report |
| `sinter validate <profile>` | Validate profile specification |
| `sinter plan <profile>` | Show requested vs effective settings |
| `sinter up <profile>` | Start llama-server |
| `sinter down` | Stop llama-server |
| `sinter status` | Show instance status |
| `sinter bench <profile>` | Benchmark performance |
| `sinter update --backend` | Update llama.cpp backend |
| `sinter exec --sandbox <cmd>` | Run command in sandbox |

All commands support `--json` for structured output.

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