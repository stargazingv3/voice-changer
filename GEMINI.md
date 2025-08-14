{
  "project": "Voice Changer",
  "description": "Real-time AI voice changer with Dockerized server and Tauri-based native client.",
  "goals": [
    "Separate client/server logic clearly in monorepo.",
    "Windows-first development, Linux-ready architecture.",
    "Low-latency real-time audio streaming.",
    "Provide clear path from MVP to advanced features."
  ],
  "fileStructureRules": {
    "client": "Tauri app with Rust backend, Web UI in /client",
    "server": "Python FastAPI + ML models in /server",
    "shared": "Protocols/config in /shared",
    "docs": "Architecture, ADRs, runbooks in /docs",
    "ci": "Workflows in /.github/workflows"
  },
  "developmentWorkflow": [
    "When editing, consider repo-wide context.",
    "Document OS-specific code clearly.",
    "Ensure client compiles with cargo tauri build on Windows.",
    "Ensure server runs in NVIDIA-enabled Docker container."
  ],
  "codeStyle": {
    "python": "PEP8 with type hints",
    "rust": "cargo fmt + clippy clean",
    "typescript": "ESLint + Prettier defaults"
  },
  "aiGuidelines": {
    "explainTradeoffs": true,
    "preferLowLatency": true,
    "avoidSecrets": true,
    "documentDecisions": true
  }
}
