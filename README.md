# Voice Changer — Local Dev Quickstart

This repo contains a Windows-first client and a Dockerized server for a real-time voice changer.

## Prereqs

- Windows 11 with WSL2 (Ubuntu)
- NVIDIA GPU (optional for MVP echo; required later for models)
- Docker Desktop with WSL integration + NVIDIA Container Toolkit

## Start the server (WSL2)

```bash
cd Docker
docker compose up --build
```

Server will listen at `http://localhost:8001`, WebSocket at `ws://localhost:8001/stream/audio`.

Health check:

```bash
curl http://localhost:8000/healthz
```

## Client (Tauri + Svelte)

Planned structure:

- `client/app`: Svelte UI
- `client/core`: Rust audio engine (WASAPI via cpal), WS transport, ring buffers

First run (to be implemented next):

```powershell
cd client
npm install
cargo tauri dev
```

## Audio settings (MVP)

- 48 kHz, mono, S16LE, 10 ms frames (480 samples)
- WebSocket init message:

```json
{ "type": "init", "sampleRate": 48000, "channels": 1, "format": "S16LE", "frameSize": 480 }
```

Then stream binary PCM frames. Server echoes frames back and emits periodic stats JSON.

# voice-changer

#Build
To build windows executable from linux:

Cross-compiler: sudo apt install mingw-w64
Install for alsa-sys crate: sudo apt-get install libasound2-dev
Install for glib-sys cate : sudo apt-get install libglib2.0-dev
Install for gdk-sys crate: sudo apt-get install libgtk-3-dev
Install for soup3-sys crate: sudo apt-get install libsoup-3.0-dev
Install for javascriptcore-rs-sys crate: sudo apt-get install libwebkit2gtk-4.1-dev

Install dependencies: npm install
Tell rust to target windows: rustup target add x86_64-pc-windows-gnu
Install Tauri-cli: cargo install cargo-binstall
                   cargo binstall tauri-cli
Install rustup: sudo apt install rustup
Initialize rustup default toolchain: rustup default stable
Build for windows: cargo build --target x86_64-pc-windows-gnu
Modify client/app/package.json tauri build --target x86_64-pc-windows-gnu
In client/app run : npm run build

