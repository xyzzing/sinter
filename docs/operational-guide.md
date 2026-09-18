# Sinter Operational Guide

## Quick Start

```bash
sinter doctor          # Check system health
sinter validate coding # Validate profile
sinter plan coding     # Plan settings
sinter up coding       # Start llama-server
sinter status          # Check status
sinter down            # Stop llama-server
```

## Commands

- `sinter doctor [--json]` - Read-only hardware/backend report
- `sinter validate <profile> [--json]` - Validate profile without loading weights
- `sinter plan <profile> [--json]` - Explain requested vs effective settings
- `sinter up <profile> [--timeout N] [--foreground]` - Start llama-server
- `sinter down [--timeout N]` - Stop the running llama-server
- `sinter status [--json]` - Show current instance status

## Profiles

Defined in `~/.config/sinter/sinter.toml` or `profiles/*.toml`.

```toml
[profiles.coding]
weights_path = "/path/to/model.gguf"
backend_binary = "/path/to/llama-server"
device = "ROCm0"
ctx_size = 131072
n_gpu_layers = 63
port = 8080
```

## Logs

- Operational: `~/.local/state/sinter/logs/` (JSON lines)
- Backend: `~/.local/state/sinter/logs/backend-<profile>.log`

## State Files

- `~/.local/state/sinter/instance.json` - Current instance
- `~/.local/state/sinter/state.json` - Supervisor state
- `/run/user/$UID/sinter/lock` - Supervisor lock

## Troubleshooting

- Port in use: `ss -tlnp | grep :8080`
- VRAM insufficient: `sinter plan <profile>`
- Backend not starting: check `backend-<profile>.log`
- Permission denied: ensure `rocm` group membership