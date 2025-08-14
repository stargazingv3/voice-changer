# Dev Setup

## Prereqs (Windows host)
- Cursor IDE
- Rust toolchain (`rustup`)
- Node.js (LTS)
- NSIS or WiX Toolset
- VB-CABLE installed
- Git
- Visual Studio Build Tools (C++)

## WSL2 (Ubuntu)
- Docker + NVIDIA Container Toolkit
- make/just
- jq
- Git

## First run
```bash
# Start server (in WSL2)
docker compose up

# Start client (on Windows)
cd client
npm install
cargo tauri dev
