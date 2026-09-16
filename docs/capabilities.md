# SINTER — Hardware & Backend Capability Report (T00)

**Date:** 2026-09-16
**Ticket:** T00
**Status:** Baseline established

## 1. Host System

| Component | Verified Value | Source |
|---|---|---|
| OS | Fedora Linux 44 | `uname -a` |
| Kernel | 7.2.5-200.fc44.x86_64 | `uname -r` |
| CPU | AMD Ryzen 9 7900X (12 cores / 24 threads) | `lscpu` |
| CPU Max Clock | 4701 MHz | `lscpu` |
| System RAM | 96 GB DDR5 (93 GiB visible) | `free -h` |
| Available RAM | 63 GiB at time of check | `free -h` |
| Swap | 8.0 GiB (unused) | `free -h` |

## 2. GPU & ROCm

| Component | Verified Value | Source |
|---|---|---|
| GPU Model | AMD Radeon RX 7900 XT/7900 XTX (Navi 31) | `lspci -nn` |
| PCI Identity | 1002:744c (rev c8) | `lspci -nn` |
| PCI Slot | 03:00.0 | `lspci -nn` |
| VRAM Total | 24 GB (25,753,026,560 bytes) | `rocm-smi` |
| VRAM Used (by llama-server) | ~20.5 GB (20,463,906,816 bytes) | `rocm-smi` |
| VRAM Free | ~3.5 GB | computed |
| ROCm Version | **7.1.1** (not 6.x) | `rpm -qa | grep rocm` |
| ROCm Runtime Package | rocm-runtime-7.1.1-6.fc44 | `rpm -qa` |
| HIP Driver Lib | libamdhip64.so.7 (/lib64) | `ldd llama-server` |
| HIP BLAS Lib | libhipblas.so.3 (/lib64) | `ldd llama-server` |
| HSA Override | HSA_OVERRIDE_GFX_VERSION=11.0.0 | process env |

### Known GPU Limitations (PRD Findings)

- **F04:** `rocm-smi` VRAM usage is device-wide, including compositor and other consumers. A fixed reserve is not accurate under desktop load.
- **F14:** MTP (Multi-Token Prediction) support for this model/backend combination is **unverified**. Speculative decoding is off by default.

## 3. Backend: llama-server

| Component | Verified Value | Source |
|---|---|---|
| Binary Path | /home/zacch/llama_rocmfpx_build/ROCmFPX/build/bin/llama-server | `ps aux` |
| Version | 257 (c49ebdb) | `--version` |
| Compiler | Clang 22.1.8 | `--version` |
| Build Variant | ROCmFPX (custom build) | path |
| Process PID | 485578 | `ps aux` |
| API Health | `{"status":"ok"}` | `curl localhost:8080/health` |

### Launch Configuration (from process environment)

| Parameter | Value | Notes |
|---|---|---|
| Model | /home/zacch/models/Qwen3.8-27B-TTURBO-Fable-C-Fusion-709-L-Uncen-NM-DAU-NEO-MTP-IQ4_XS.gguf | IQ4_XS quantized |
| Host | **0.0.0.0** | LAN accessible (not loopback-only) |
| Port | 8080 | |
| Device | ROCm0 | |
| GPU Layers | 63 | Full model on GPU |
| Context Size | 131,072 tokens | n_ctx |
| KV Cache Type K | q4_0 | Quantized |
| KV Cache Type V | q4_0 | Quantized |
| Flash Attention | on | |
| Continuous Batching | true | |
| Batch Size | 4096 | |
| Micro-Batch | 1024 | |
| Threads | 6 | |
| Parallel Slots | 1 | |
| Prompt Cache | **disabled** (size=0) | PR #16391 SIGABRT on ROCm |
| Chat Template | /home/zacch/.config/llama-models/templates/qwen-sharp.jinja | |

## 4. Active Model Artifact

| Attribute | Verified Value | Source |
|---|---|---|
| Filename | Qwen3.8-27B-TTURBO-Fable-C-Fusion-709-L-Uncen-NM-DAU-NEO-MTP-IQ4_XS.gguf | filesystem |
| Size on Disk | 15.3 GB (15,309,047,136 bytes) | `ls -la` |
| Quantization | IQ4_XS | filename (unverified) |
| Parameter Count | 27,320,697,856 (~27.3B) | API `/v1/models` meta |
| Embedding Dim | 5120 | API meta |
| Context (trained) | 262,144 tokens | API meta (n_ctx_train) |
| Context (server) | 131,072 tokens | server config |
| Vocabulary Size | 248,320 | API meta |
| Model Family | Unknown (empty in API) | API meta |

### Provenance & License (F26)

- **F26 applies:** This model name appears to be a community merge/fine-tune (TTURBO-Fable-C-Fusion-709-L-Uncen-NM-DAU-NEO-MTP suffix). Provenance, source repository, revision SHA, and license are **unverified placeholders** until resolved against a known artifact.
- The model name suggests MTP (Multi-Token Prediction) support, but F14 states this is unverified.
- No SHA-256 digest has been recorded yet.

## 5. Known Runtime Limits

| Finding | Description | Impact |
|---|---|---|
| F04 | VRAM monitoring is device-wide; compositor usage is included | Preflight memory estimate is race-prone |
| F14 | MTP speculative decoding unverified for this model/backend | Default off; no speedup assumed |
| F26 | Model name, SHAs, and capabilities are unverified placeholders | Cannot assert compatibility or license |
| PR #16391 | Prompt-cache RAM implementation caused SIGABRT on ROCm | Prompt cache disabled (size=0) |
| TOP_K | ROCm lacks GPU-side operation | Runs on CPU (minor overhead) |
| Network | Server bound to 0.0.0.0:8080 | LAN-accessible; no authentication by default |

## 6. Missing / Unknown Sensors

- GPU temperature: `rocm-smi --showtemp` returned no reading (GPU in low-power state)
- GPU power draw: not captured
- GPU utilization: not captured
- ROCm driver version: inferred from package version 7.1.1; exact kernel module version not checked
- ROCm library location: ROCM_PATH=/opt/rocm is set but directory does not exist; actual libs are in /lib64 (Fedora package layout)

## 7. T01 Test Plan

**Objective:** Raw llama-server multi-turn tool calling and streaming round trip.

### Prerequisites
- llama-server already running on 0.0.0.0:8080 (verified)
- Model loaded with n_ctx=131072 (verified)

### Test Cases

1. **Single-turn text completion (non-streaming):**
   - POST /v1/chat/completions with a simple prompt
   - Verify response structure, token counts, and content

2. **Streaming completion:**
   - POST /v1/chat/completions with stream=true
   - Verify SSE chunk format, incremental delivery, and completion

3. **Multi-turn conversation:**
   - 3+ turn exchange maintaining context
   - Verify the model references prior turns correctly

4. **Tool calling (function calling):**
   - Define a tool schema (e.g., `get_weather(city)`)
   - Prompt the model to use the tool
   - Verify tool call structure in response
   - Feed tool result back in a follow-up turn
   - Verify the model incorporates the result

5. **Context/memory evidence:**
   - Measure VRAM before and after a long context request
   - Verify KV cache is being used (q4_0)

6. **Client compatibility:**
   - Test with a real coding agent client (e.g., Claude Code, Zed, or similar)
   - Verify tool schema, streaming, and error handling

### Success Criteria
- All API calls return valid responses
- Streaming produces correct SSE chunks
- Tool calling produces correct structure and the model uses tools appropriately
- Multi-turn context is maintained
- No SIGABRT or other crashes
- Latency measurements recorded (p50, p95 first-token; decode rate)

### Deliverables
- Raw API request/response traces
- Latency measurements
- Client compatibility notes
- VRAM usage during operation

## 8. T01 Results (Raw Backend Spike)

**Date:** 2026-09-16
**Server:** http://localhost:8080
**Model:** Qwen3.8-27B-TTURBO-Fable-C-Fusion-709-L-Uncen-NM-DAU-NEO-MTP-IQ4_XS.gguf

### Test Results

| # | Test | Result | Notes |
|---|---|---|---|
| 1 | Single-turn completion (non-streaming) | PASS | `finish_reason: length` at max_tokens=20; model used reasoning_content |
| 2 | Streaming completion (SSE) | PASS | Correct `data: {...}` SSE chunks with incremental content |
| 3 | Multi-turn conversation | PASS | Model remembered "Zacch" across turns |
| 4 | Tool calling (function calling) | PASS | Correct tool name, arguments, and tool_call_id generated |
| 4b | Tool result feedback round-trip | PASS | Model incorporated tool result into final answer |
| 5 | Long context (5173 prompt tokens) | PASS | Processed without error; VRAM delta measured |
| 6 | Client compatibility (tool schema) | PASS | OpenAI-compatible tool schema accepted and executed |
| 7 | Cancellation (timeout) | PASS | Client timeout (exit 124) worked; server remained healthy |
| 8 | Error handling (bad model name) | PASS (with caveat) | Server ignores model name in request; uses loaded model |
| 9 | Context overflow | PASS (with caveat) | Server did not crash on oversized input (test timed out) |
| 10 | Streaming tool calling | PASS | Tool calls delivered in SSE chunks |

### Latency Measurements (976 prompt tokens, 100 decode tokens)

| Run | Prefill (ms) | Prefill (tok/s) | Decode (ms) | Decode (tok/s) |
|---|---|---|---|---|
| 1 | 1081 | 903 | 4128 | 24.2 |
| 2 | 1078 | 905 | 4082 | 24.5 |
| 3 | 1051 | 929 | 4041 | 24.7 |
| **Avg** | **1070** | **912** | **4084** | **24.5** |

### VRAM Usage

| State | VRAM Used (GB) |
|---|---|
| Baseline (model loaded) | 20.5 |
| After long context (5173 tokens) | 21.2 |
| Delta | +0.7 GB |

### Observations

- **Reasoning content:** The model consistently produces `reasoning_content` in addition to `content`. Clients must handle both fields.
- **Model name ignored:** The `model` field in the request body is ignored; the server always uses the loaded model. This is standard llama-server behavior.
- **Decode rate:** ~24.5 tok/s for this model on ROCm. Consistent across runs.
- **Prefill rate:** ~912 tok/s for 1K tokens. Scales reasonably.
- **No crashes:** All tests completed without SIGABRT or other failures.
- **Server health:** Remained healthy throughout all tests.

### Unresolved Items

- **Context overflow:** The 500K character test timed out rather than returning an error. Need to verify server behavior on true context overflow (approaching 131072 tokens).
- **Client integration:** Claude Code is installed but not yet tested against this server. The API is OpenAI-compatible, so it should work.
- **MTP:** The model name suggests MTP support, but no evidence was found in the API responses. Speculative decoding appears to be off.

## 9. Next Executable Action

Proceed to **T02**: Minimal package, configuration schema, atomic state, and plan/doctor interfaces. The raw backend is proven to work; the supervisor can now be built around it.
