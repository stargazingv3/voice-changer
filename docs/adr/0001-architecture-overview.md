**Date:** 2025-08-13  
**Status:** Accepted  
**Deciders:** [Your Name]  
**Context:**  
We need a cross-platform architecture for a real-time AI voice changer that:
- Runs the inference server in Docker (deployable locally or on GPU cloud)
- Runs a native client on Windows without requiring Python env setup
- Can output modified audio to a virtual microphone for use in games and VoIP

**Decision:**  
- **Client**: Native app (Tauri, Rust backend, Web UI) for audio I/O, DSP, settings, and virtual mic integration.
- **Server**: Python + PyTorch inside NVIDIA-enabled Docker container; FastAPI control plane; streaming via WebSockets initially, later gRPC/WebRTC.
- **Shared**: Single GitHub monorepo with `/shared` folder for protocols/config.
- **Packaging**: Client packaged with NSIS/WiX; Server packaged as GPU-ready Docker image.
- **Virtual Mic**: Use VB-CABLE for MVP; custom signed driver in later phase.
- **Transport**:  
  - MVP: WebSockets  
  - Phase 2: gRPC bidi  
  - Phase 3: WebRTC

**Consequences:**  
- Simple local dev loop (Docker server + Tauri client).
- Predictable CI builds for both installer and server image.
- Clear path to scale from local-only to cloud multi-user hosting.
