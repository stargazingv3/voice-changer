**Date:** 2025-08-13  
**Status:** Accepted  

**Decision:**  
Monorepo with these top-level dirs:

  client/                      # Windows UI + audio
    app/                       # Tauri UI (src, assets)
    core/                      # Rust audio engine, transport, buffers
    virtual_mic/               # driver assets & installer (Phase 3)
    packaging/                 # NSIS/WiX configs, code signing
  server/                      # Dockerized inference
    api/                       # control plane (FastAPI), auth, presets
    stream/                    # audio streaming endpoints (WS, gRPC)
    pipeline/                  # VC and ASR→TTS pipeline runners
    models/                    # model loaders, TRT engines, caching
    config/                    # model & pipeline configs, voices
    observability/             # metrics, logs, tracing
    Dockerfile
    docker-compose.yml         # dev stack (CPU/GPU profiles)
  shared/
    proto/                     # protobuf/IDL (for gRPC phase)
    messages/                  # schemas if using JSON/Flatbuffers
    presets/                   # JSON voice & DSP presets
  tools/
    ci/                        # GH Actions workflows
    scripts/                   # dev scripts (just/make/pwsh)
  docs/
    adr/                       # Architecture Decision Records
    runbooks/                  # ops, release, driver signing
  README.md

  
**Consequences:**  
- Keeps protocols/config in sync between client/server.
- Single repo means simpler CI/CD pipeline.
- Allows Cursor IDE to open full stack in one workspace.
