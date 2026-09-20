# Sinter Portability Cleanup — Local Coding-Agent Implementation Plan

## Objective

Remove all developer-specific `/home/zacch` paths from Sinter’s executable code, tests, shipped profiles, and public documentation. Make a fresh download usable on another Linux workstation without editing source code or discovering private filesystem layout.

Sinter is an out-of-band local inference supervisor for `llama-server` on AMD ROCm. Preserve its design boundaries: do not add an HTTP proxy, UI, multi-user service, or backend abstraction rewrite in this task.

## Product Decision

### Chosen configuration model

Use **user-scoped XDG configuration** as the canonical location for live configuration:

```text
~/.config/sinter/
├── config.toml
└── profiles/
    └── coding.toml
```

Ship only templates and examples in the repository/package:

```text
profiles/
└── coding.toml.example
```

Do **not** keep a gitignored live `profiles/coding.toml` in the repository. A downloadable tool should not require users to understand repository-local overrides, hidden files, or Git ignore behavior. A user-level config location also survives upgrades and keeps models, paths, and hardware-specific settings out of source control.

### Why this is best for a new user

- It follows the existing `DEFAULT_CONFIG_DIR = Path.home() / ".config" / "sinter"` direction.
- It prevents personal model paths and local build paths from being accidentally committed.
- It supports `pipx`, editable installs, source clones, package upgrades, and future system packages consistently.
- It lets `sinter setup` create an actual profile from detected software, rather than asking a user to edit code.
- It keeps the source repository safe to share and suitable for CI.

## Scope

### In scope

1. Eliminate `/home/zacch` from executable source, tests, shipped profiles, and public documents.
2. Centralize discovery of `llama-server`, `llama-bench`, llama.cpp source, and optional model paths.
3. Make explicit profile values take precedence over discovery.
4. Add environment-variable overrides for headless automation and CI.
5. Convert the committed `profiles/coding.toml` into a portable example.
6. Make integration tests portable and opt-in for real hardware.
7. Add a test that prevents developer-specific filesystem paths from re-entering the repository.
8. Redact public documents that expose the prior home path.
9. Update installation and operational documentation so a new user can run setup, validate, plan, and start a profile.

### Explicitly out of scope

- Changing Sinter’s out-of-band supervisor architecture.
- Adding a proxy between clients and `llama-server`.
- Adding vLLM support.
- Changing GGUF memory formulas or profile tuning values.
- Auto-downloading model weights.
- Automatically compiling llama.cpp in this portability PR.
- Introducing a heavyweight dependency-injection framework or a new configuration library.

## Current Findings

The following repository locations currently contain machine-specific `/home/zacch` paths and must be addressed:

| Location | Required treatment |
|---|---|
| `src/sinter/config.py` | Remove hardcoded `backend_binary` default |
| `src/sinter/hardware.py` | Remove hardcoded `llama-server` fallback |
| `src/sinter/bench.py` | Remove hardcoded `llama-bench` candidate |
| `src/sinter/update.py` | Remove hardcoded llama.cpp source candidates |
| `profiles/coding.toml` | Replace with a committed portable example; do not retain personal paths |
| `tests/integration/test_acceptance.py` | Replace hardcoded hardware/model paths with opt-in env-driven fixture(s) |
| `docs/capabilities.md` | Redact private absolute paths while preserving meaningful capability information |
| `docs/handover.md` | Redact private absolute paths while preserving reproducibility-relevant hashes/versions where present |

## Required Design

## 1. Add a single discovery module

Create `src/sinter/discovery.py` using only the Python standard library.

It must own all executable/artifact discovery so no other module embeds developer-machine paths.

### Suggested public API

```python
from pathlib import Path


def find_llama_server(explicit: Path | None = None) -> Path | None:
    ...


def find_llama_bench(explicit: Path | None = None) -> Path | None:
    ...


def find_llama_cpp_source(explicit: Path | None = None) -> Path | None:
    ...


def resolve_path_from_env(variable: str) -> Path | None:
    ...
```

Names can differ if the repository style suggests better names, but preserve the single responsibility: discovery logic belongs in one module.

### Discovery precedence

For each executable or source directory, use this order:

1. An explicit profile/config value.
2. A documented environment override.
3. `PATH` discovery using `shutil.which`.
4. Stable, generic system locations only.
5. Return `None` with a targeted remediation message; never invent a home-directory path.

Generic system locations may include:

```text
/usr/local/bin/llama-server
/usr/bin/llama-server
/opt/llama.cpp/bin/llama-server
/usr/local/bin/llama-bench
/usr/bin/llama-bench
/usr/local/src/llama.cpp
/opt/llama.cpp
```

Do not scan arbitrary directories under the user’s home directory. It is slow, surprising, privacy-unfriendly, and unsuitable for deterministic operation.

### Environment variables

Implement and document:

| Variable | Meaning |
|---|---|
| `SINTER_LLAMA_SERVER` | Absolute path to `llama-server` |
| `SINTER_LLAMA_BENCH` | Absolute path to `llama-bench` |
| `SINTER_LLAMA_CPP_SOURCE` | Absolute path to a llama.cpp source tree |
| `SINTER_WEIGHTS` | Optional default model GGUF path used only by setup/test flows; a profile remains authoritative at runtime |
| `SINTER_CONFIG_DIR` | Optional override for the XDG-style configuration directory, useful in CI and isolated testing |

Validate environment-path overrides: they must be absolute paths and must exist. Executable overrides must be executable regular files. Source overrides must be directories. Return actionable errors; do not silently fall back after an explicitly supplied bad value.

## 2. Make configuration user-scoped

Retain the current default configuration concept, but make it explicit and testable:

```python
DEFAULT_CONFIG_DIR = Path(os.environ.get("SINTER_CONFIG_DIR", Path.home() / ".config" / "sinter"))
DEFAULT_STATE_DIR = Path.home() / ".local" / "state" / "sinter"
DEFAULT_RUNTIME_DIR = Path("/run/user") / str(os.getuid()) / "sinter"
```

If the project already supports config directory injection, do not break it. Prefer `platformdirs` only if it is already a project dependency; otherwise stay standard-library-only for this patch.

### `ProfileSpec` behavior

- `weights_path` remains required for a runnable profile.
- `backend_binary` must become optional at the dataclass level.
- Validation resolves `backend_binary` by profile value first, then discovery.
- A missing resolved binary is a validation error with this remedy: set `backend_binary` in the profile, set `SINTER_LLAMA_SERVER`, or put `llama-server` on `PATH`.
- Do not set a machine-specific default in the dataclass.

## 3. Improve `sinter setup`

Make `sinter setup` the supported onboarding path for a downloaded copy.

### Required behavior

1. Create `~/.config/sinter/profiles/` if missing.
2. Detect `llama-server` through `find_llama_server()`.
3. Optionally use `SINTER_WEIGHTS` if supplied and valid.
4. Generate a profile at `~/.config/sinter/profiles/coding.toml` only after presenting/printing the chosen fields.
5. Refuse to overwrite an existing profile unless an explicit `--force` flag is supplied.
6. If no backend is found, create no broken runnable profile. Instead print the exact paths checked and a copy-ready config example.
7. Print the next commands:

```bash
sinter doctor
sinter validate coding
sinter plan coding
sinter up coding
```

### Setup command interface

Maintain backward compatibility where possible. Add only small, explicit options if absent:

```bash
sinter setup \
  --profile coding \
  --backend /path/to/llama-server \
  --weights /path/to/model.gguf
```

Optional flags must feed the same precedence model as profile values; do not create a parallel configuration system.

## 4. Replace the committed profile

Delete `profiles/coding.toml` and add `profiles/coding.toml.example`.

Use portable placeholder values and comments that explain required edits. Do not embed a real model name, user name, filesystem layout, API endpoint, or server bound to `0.0.0.0`.

Suggested content:

```toml
# Copy this through `sinter setup`, or create
# ~/.config/sinter/profiles/coding.toml and set real paths.

[profiles.coding]
alias = "coding"
weights_path = "/absolute/path/to/model.gguf"
backend_binary = "/absolute/path/to/llama-server"
device = "ROCm0"
n_gpu_layers = 0
ctx_size = 16384
cache_type_k = "q4_0"
cache_type_v = "q4_0"
flash_attn = true
host = "127.0.0.1"
port = 8080
```

Do not claim that `n_gpu_layers = 0`, `ctx_size = 16384`, or cache types are universally correct; they are safe placeholders. The README must direct users to `sinter plan` and hardware-specific tuning.

## 5. Update source modules

### `src/sinter/config.py`

- Remove the `/home/zacch/.../llama-server` default.
- Make `backend_binary: Path | None = None`.
- Resolve it via the discovery module in validation or a clearly named resolution step.
- Keep parsing and schema validation separate from executable discovery if possible.
- Add tests for profile override, env override, `PATH` discovery, and missing backend.

### `src/sinter/hardware.py`

- Replace `which` subprocess usage and the private fallback with `find_llama_server()`.
- Ensure `doctor` reports both the discovered binary and the discovery source if practical, e.g. `profile`, `SINTER_LLAMA_SERVER`, `PATH`, or system path.
- A missing backend must be represented as “not found,” not as an exception that breaks unrelated hardware reporting.

### `src/sinter/bench.py`

- Replace private candidates with `find_llama_bench()`.
- Produce a clear message that benchmark functionality requires `llama-bench`, and state the override variable.

### `src/sinter/update.py`

- Replace private source candidates with `find_llama_cpp_source()`.
- If no source tree is resolved, fail the update operation before doing any mutation and explain how to set `SINTER_LLAMA_CPP_SOURCE` or configure the source path.

### `src/sinter/setup.py`

- Use discovery functions; do not duplicate candidate lists.
- Write user-level profile configuration safely and atomically.
- Never place a personal profile into the checked-out repository.

## 6. Make tests portable

### Unit tests

Add `tests/unit/test_discovery.py` covering:

- Explicit valid path wins.
- Explicit invalid path fails clearly without fallback.
- Environment override wins over `PATH`.
- `PATH` discovery works.
- Generic system-path fallback works when it exists.
- Nothing found returns `None` or a controlled domain-specific result.
- Private paths are not present in discovery constants.

Use `tmp_path`, `monkeypatch`, and fake executable files with executable permissions. Do not rely on any installed model, ROCm device, or local llama.cpp build.

Update config/hardware/bench/update tests to mock the discovery boundary instead of mocking specific `/home/...` paths.

### Integration tests

Refactor `tests/integration/test_acceptance.py` into two categories:

1. **Portable mocked acceptance path**: always runs in CI. It must exercise `validate → plan → up → health → status → down` using a controlled fake backend.
2. **Real-hardware smoke path**: opt-in and skipped unless all requirements are explicitly supplied, for example:

```bash
SINTER_RUN_REAL_HARDWARE_TESTS=1 \
SINTER_LLAMA_SERVER=/absolute/path/to/llama-server \
SINTER_WEIGHTS=/absolute/path/to/model.gguf \
pytest -m real_hardware
```

Mark the real test with `pytest.mark.real_hardware`. Ensure it does not run by default in GitHub Actions.

## 7. Add a repository hygiene regression test

Add `tests/unit/test_portability_hygiene.py` or an equivalent CI script.

It must scan tracked, relevant text files under at least:

```text
src/
tests/
profiles/
docs/
README.md
ARCHITECTURE.md
SPEC.md
```

It must fail if any forbidden private-path pattern appears:

```text
/home/zacch
/home/<actual-user-name>
```

At minimum block `/home/zacch`. Do not write a simplistic blanket rule that blocks valid documentation about generic `/home/<user>` paths; use an allowlisted, documented generic placeholder such as `/home/<user>` if needed.

Also scan for the concrete model filename currently in the repo if it is intended to be private or non-redistributable.

## 8. Redact documentation

Public documentation should preserve useful reproducibility facts while removing personal filesystem locations and overly personal model artifacts.

### `docs/capabilities.md`

Replace private paths with neutral placeholders:

```text
llama-server binary: [local path redacted]
model artifact: [local path redacted]
```

Retain non-sensitive facts where still correct:

- Backend commit/build identifier
- GPU/ROCm facts
- Tested model architecture/quantization only if redistribution/license status is clear
- Measured performance values with date/context

### `docs/handover.md`

Replace backend absolute paths and local server URLs as needed. Do not present `0.0.0.0:8080` as a safe default; the product architecture specifies loopback. Document the operational server address as `127.0.0.1:<port>`.

### README and install guide

Add a short “First run” section:

```bash
pip install -e .
sinter doctor
sinter setup --profile coding --backend /path/to/llama-server --weights /path/to/model.gguf
sinter validate coding
sinter plan coding
sinter up coding
```

State that profiles live under `~/.config/sinter/profiles/` and that examples in the repository are templates only.

## 9. CI requirements

Ensure the existing CI runs:

```bash
python -m pytest
ruff check .
```

Add the portability hygiene test to the normal test suite. Do not require ROCm, a GPU, a GGUF model, or llama.cpp binaries in CI.

If CI lacks a packaging smoke test, add one that creates a clean virtual environment, installs the package, and verifies:

```bash
sinter --help
sinter doctor --json
```

The smoke test may report that no backend was found; it must not fail merely because a local inference stack is absent.

## Acceptance Criteria

The work is complete only when all of the following are true:

1. `git grep -n '/home/zacch'` returns no matches in the working tree, excluding only an explicit migration-history record if one is intentionally retained; prefer zero results.
2. `git grep -n 'Qwen3.8-27B-TTURBO-Fable-C-Fusion-709-L-Uncen-NM-DAU-NEO-MTP-IQ4_XS'` has no result unless licensing and public distribution were deliberately confirmed.
3. A fresh user can install and run `sinter doctor` with no existing Sinter config.
4. A user can make a profile using `sinter setup` without modifying source files.
5. An explicit profile backend path wins over `SINTER_LLAMA_SERVER`; `SINTER_LLAMA_SERVER` wins over `PATH`; `PATH` wins over generic system paths.
6. An invalid explicit path errors clearly and does not silently select another executable.
7. `sinter validate coding` tells a user exactly how to fix absent backend/model paths.
8. Default tests require no GPU, ROCm, private model, private build, or nonstandard home directory.
9. The real-hardware test is explicitly opt-in.
10. CI fails if a new `/home/zacch` reference is committed.
11. No runtime code contains a developer-specific filesystem path.
12. The design remains an out-of-band supervisor; no proxy or unrelated capability is added.

## Verification Commands

Run these before proposing the implementation as complete:

```bash
python -m pytest
ruff check .
python -m build
python -m pip install --force-reinstall dist/*.whl
sinter --help
sinter doctor --json

git grep -n '/home/zacch' || true
git grep -n 'Qwen3.8-27B-TTURBO-Fable-C-Fusion-709-L-Uncen-NM-DAU-NEO-MTP-IQ4_XS' || true
```

For a real workstation only, after manually confirming paths:

```bash
export SINTER_LLAMA_SERVER=/absolute/path/to/llama-server
export SINTER_WEIGHTS=/absolute/path/to/model.gguf
sinter setup --profile coding --backend "$SINTER_LLAMA_SERVER" --weights "$SINTER_WEIGHTS"
sinter validate coding
sinter plan coding
```

Do not run `sinter up coding` automatically during the coding-agent task unless the user explicitly asks, because it starts a real inference process and consumes GPU memory.

## Implementation Sequence

1. Read `SPEC.md`, `ARCHITECTURE.md`, `SKILLS.md`, `src/sinter/config.py`, `src/sinter/setup.py`, and existing tests before editing.
2. Create the discovery module and its unit tests first.
3. Convert configuration defaults and consumers to use discovery.
4. Refactor integration tests into portable and opt-in hardware paths.
5. Replace the committed profile with an example and update setup behavior.
6. Redact docs and improve first-run instructions.
7. Add hygiene regression coverage.
8. Run all verification commands.
9. Report changed files, test results, unresolved environmental limitations, and any behavior that needs a human decision.

## Guardrails for the Coding Agent

- Make no external network calls.
- Do not download a model or compile llama.cpp.
- Do not launch `llama-server` or run real-GPU tests unless explicitly instructed after the patch is reviewed.
- Preserve public APIs unless a breaking change is necessary to remove the unsafe default; if one is necessary, document it in `CHANGELOG.md`.
- Keep new dependencies at zero unless a dependency already present in `pyproject.toml` is required.
- Use a dedicated branch and one focused pull request named `portability/remove-machine-specific-paths`.
- Do not mix formatting-only refactors or Phase 2 feature work into this change.
