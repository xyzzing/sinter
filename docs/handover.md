# SINTER — Handover Document

**Date:** 2026-09-16
**Completed:** T00 (capability report), T01 (raw backend spike), T02 (minimal package, config schema, atomic state, plan/doctor interfaces), T03 (ownership, lock, state machine, launch/readiness/stop)
**Next:** T04 (bounded GGUF validation and memory/profile qualification)

## 1. What Has Been Done

### T00 — Hardware/Backend Capability Report
- Inspected repository: only `docs/prd.md` and `SKILLS.md` exist
- Collected verified hardware facts (see `docs/capabilities.md` Section 1-4)
- Identified active llama-server build: v257 (c49ebdb), ROCmFPX, bound to 0.0.0.0:8080
- Identified active model: Qwen3.8-27B-TTURBO-Fable-C-Fusion-709-L-Uncen-NM-DAU-NEO-MTP-IQ4_XS.gguf (15.3 GB, IQ4_XS)
- Corrected known environment facts: ROCm is 7.1.1 (not 6.x), ROCM_PATH is stale
- Established baseline capability report

### T01 — Raw Backend Spike
- Ran 10 API tests against the running llama-server
- All tests passed: single-turn, streaming, multi-turn, tool calling, cancellation, error handling
- Latency: prefill ~912 tok/s, decode ~24.5 tok/s
- VRAM: 20.5 GB baseline, +0.7 GB for 5K token context
- Server remained healthy throughout all tests
- API is OpenAI-compatible

## 2. Current State

### Files
- `docs/prd.md` — Product Requirements Document (v6.0)
- `docs/capabilities.md` — Hardware capability report + T01 results
- `SKILLS.md` — Pre-existing skill documentation

### Running Services
- llama-server v257 on 0.0.0.0:8080 (PID 485578)
- Model: Qwen3.8-27B-TTURBO-Fable-C-Fusion-709-L-Uncen-NM-DAU-NEO-MTP-IQ4_XS.gguf
- Config: 63 GPU layers, ctx=131072, KV cache q4_0, flash attn on

### Known Limitations
- F04: VRAM monitoring is device-wide
- F14: MTP speculative decoding unverified
- F26: Model provenance/license unverified
- PR #16391: Prompt cache disabled (SIGABRT on ROCm)
- TOP_K: ROCm lacks GPU-side op (runs on CPU)

## 3. What Needs to Be Done Next

### T02 — Minimal Package & Interfaces
**Scope:**
- Create minimal Python package structure (Python 3.11+)
- Configuration schema (TOML input)
- Atomic state management
- `sinter doctor --json` — read-only device/capability report
- `sinter profile validate coding` — validate profile schema without loading weights
- `sinter plan coding --json` — explain requested vs effective settings

**Dependencies:** None (T01 is complete)

**Acceptance evidence:**
- Malformed configuration tests pass
- Missing-sensor tests pass
- Reproducible install

**Suggested executor:** GLM/ZCode

### Subsequent Tickets
- T03: Ownership, lock, state machine, launch/readiness/stop
- T04: Bounded GGUF validation and memory/profile qualification
- T05: One real client acceptance journey and private logging
- T06: Adversarial code review and repair
- T07: Baseline comparison, install/uninstall, operational guide

## 4. Available Skills in This Session

The following skills are available but **none are relevant** to SINTER development:

| Skill | Relevance |
|---|---|
| animate | ❌ Frontend animation |
| animate-expo | ❌ React Native animation |
| animation-vocabulary | ❌ Animation terminology |
| apple-design | ❌ Apple design patterns |
| ask-sonner | ❌ Toast notification library |
| better-ui | ❌ UI polish |
| design-taste-frontend | ❌ Landing page design |
| emil-design-eng | ❌ UI polish philosophy |
| find-animation-opportunities | ❌ Animation audit |
| find-skills | ❌ Skill discovery |
| improve-animations | ❌ Animation audit |
| mobile-native | ❌ Mobile web optimization |
| write-swift | ❌ Swift programming |

**Relevant skills needed but not available:**
- Python backend development
- ROCm/HIP GPU programming
- llama.cpp integration
- CLI tool design
- System service management (systemd)
- Memory profiling and optimization

## 5. Key Environment Facts

| Fact | Value |
|---|---|
| OS | Fedora 44, kernel 7.2.5-200.fc44.x86_64 |
| CPU | AMD Ryzen 9 7900X (12c/24t) |
| RAM | 96 GB DDR5 |
| GPU | AMD Radeon RX 7900 XT/XTX (Navi 31), 24 GB VRAM |
| ROCm | 7.1.1 |
| llama-server | v257 (c49ebdb), ROCmFPX build |
| Model | Qwen3.8-27B-TTURBO-Fable-C-Fusion-709-L-Uncen-NM-DAU-NEO-MTP-IQ4_XS.gguf |
| Server URL | http://0.0.0.0:8080 |
| ROCM_PATH | /opt/rocm (stale; actual libs in /lib64) |
| HSA_OVERRIDE_GFX_VERSION | 11.0.0 |

## 6. Verification Commands

```bash
# Server health
curl -s http://localhost:8080/health

# Model info
curl -s http://localhost:8080/v1/models | python3 -m json.tool

# Quick completion test
curl -s -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "Qwen3.8-27B-TTURBO-Fable-C-Fusion-709-L-Uncen-NM-DAU-NEO-MTP-IQ4_XS.gguf", "messages": [{"role": "user", "content": "Hello"}], "max_tokens": 10}'

# VRAM usage
rocm-smi --showmeminfo vram

# llama-server process
ps aux | grep llama-server
```

## 7. Risks & Caveats

- **ROCm version:** 7.1.1, not 6.x as documented. Verify ROCm 6.x vs 7.x compatibility for any driver-related work.
- **ROCM_PATH:** Environment variable points to non-existent /opt/rocm. Actual libraries are in /lib64. This may confuse tools that rely on ROCM_PATH.
- **Model provenance:** The model name suggests it's a community merge. No source repository, SHA, or license has been verified (F26).
- **MTP support:** Unverified (F14). The model name includes "MTP" but no evidence was found in API responses.
- **Network exposure:** Server is bound to 0.0.0.0:8080 (LAN accessible) with no authentication by default.

## 8. Handover Notes

This is a **local inference supervisor** project for a single developer using an AMD workstation. The goal is to make starting/recovering local coding sessions more reliable than the current pinned llama-server command.

The raw backend is proven to work (T01). The next step is building the supervisor layer (T02+).

Key design principles from the PRD:
- Single user, single machine, single GPU
- Python 3.11+ control plane
- Foreground mode first, optional systemd service later
- No custom proxy or intent router for MVP
- Explicit profile selection (no silent model swapping)
- Atomic writes, private control socket under XDG_RUNTIME_DIR
- No shell command strings in model metadata

## 9. Contact / Context

This handover is for the next agent or developer taking over SINTER development. All verified facts are in `docs/capabilities.md`. The product contract is in `docs/prd.md`. Start with T02.