# Sinter Hardware & Environment Observations (T00)

## 1. System Inventory
- Host Kernel: 7.2.5-200.fc44.x86_64
- OS / Distro: Fedora Linux 44 (KDE Plasma Desktop Edition)
- ROCm Version: 7.1.1
- GPU PCI ID: 1002:744c
- Observed Total VRAM: 24.0 GB

## 2. Pinned Backend Discovery
- llama-server Binary Path: /home/zacch/llama_rocmfpx_build/ROCmFPX/build/bin/llama-server
- llama.cpp Commit / Build ID: v257 (c49ebdb), ROCmFPX build
- Supported CLI Flags: OpenAI-compatible API; standard llama-server flags

## 3. Real Model Identification
- Artifact Path: /home/zacch/models/Qwen3.8-27B-TTURFO-Fable-C-Fusion-709-L-Uncen-NM-DAU-NEO-MTP-IQ4_XS.gguf
- Model Name & Architecture: Qwen3.8-27B-TTURBO-Fable-C-Fusion-709-L-Uncen-NM-DAU-NEO-MTP-IQ4_XS (IQ4_XS quantization)
- SHA256 / Checksum: (to be computed)
- License Record: (to be verified — F26 open item)

## 4. Active Backend Process
- PID: 485578
- Binding: 0.0.0.0:8080 (LAN accessible)
- Config: 63 GPU layers, ctx=131072, KV cache q4_0, flash attention enabled

## 5. Known Limitations
- F04: VRAM monitoring is device-wide
- F14: MTP speculative decoding unverified
- F26: Model provenance/license unverified
- PR #16391: Prompt cache disabled (SIGABRT on ROCm)
- TOP_K: ROCm lacks GPU-side op (runs on CPU)