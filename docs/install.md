# Sinter Installation Guide

## Prerequisites

- Linux (tested on Fedora 44)
- Python 3.11+
- ROCm stack 7.1.1+ (for AMD GPU support)
- ROCm-enabled llama.cpp build with `llama-server`
- Model weights in GGUF format

## From Source

```bash
git clone https://github.com/zac-ch/sinter.git
cd sinter
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Verify

```bash
sinter --version
sinter doctor
```

## XDG Directories

| Directory | Purpose | Default |
|-----------|---------|---------|
| `XDG_CONFIG_HOME/sinter` | Configuration | `~/.config/sinter` |
| `XDG_STATE_HOME/sinter` | State, logs | `~/.local/state/sinter` |
| `XDG_RUNTIME_DIR/sinter` | Lock, PID | `/run/user/$UID/sinter` |

## Uninstall

```bash
rm -rf .venv
pip uninstall sinter  # if system-wide
rm -rf ~/.config/sinter ~/.local/state/sinter  # optional
```