---

# Voice Changer — Development Checklist

## **Infrastructure & Performance**

* **Container Optimization**

  * [ ] Reduce Docker image size for `server/` (multi-stage builds, slim base).
  * [ ] Enable NVIDIA Container Toolkit for GPU access.
  * [ ] Preload models into GPU memory at container start (warm start).
  * [ ] Add Prometheus metrics for per-stage latency and GPU utilization.
* **Local/Cloud Deployment**

  * [ ] Docker Compose for local (WSL2) setup.
  * [ ] GPU-optimized image build for AWS (g5.xlarge/L4).
  * [ ] Implement environment profiles (`local`, `cloud`).
  * [ ] Blue/green deploy support for safe upgrades.
* **Performance Targets**

  * [ ] VC pipeline: ≤ 80 ms p95 latency.
  * [ ] ASR→TTS pipeline: ≤ 300 ms p95 latency.
  * [ ] Cold start < 3 seconds after container launch.

---

## **Client Application (Windows-First)**

* **Audio I/O**

  * [ ] WASAPI capture/playback implementation.
  * [ ] Device selector for mic/output.
  * [ ] Ring buffer to smooth jitter.
  * [ ] Use Opus for size etc.
* **UI & Controls**

  * [ ] Mode toggle: VC ↔ ASR→TTS.
  * [ ] Latency and quality indicators.
  * [ ] Voice preset selector.
* **Virtual Microphone**

  * [ ] Integrate VB-CABLE (MVP).
  * [ ] Custom signed virtual mic driver (post-MVP).
  * [ ] Fallback to WASAPI loopback if driver not available.
* **Packaging**

  * [ ] Build signed installer (NSIS/WiX).
  * [ ] Auto-update channel.
  * [ ] Crash reporting integration.

---

## **Voice Processing Pipelines**

* **VC (Low Latency)**

  * [ ] Model integration (encoder → timbre/style → vocoder).
  * [ ] Optimize frame sizes for minimal delay.
  * [ ] Test multiple voices for naturalness.
* **ASR→TTS (Privacy Mode)**

  * [ ] Streaming ASR with partial hypothesis output.
  * [ ] Low-latency TTS with voice presets.
  * [ ] Cross-fade between chunks for smoother speech.
* **Quality Assurance**

  * [ ] A/B test between modes.
  * [ ] Golden sample regression tests.
  * [ ] Latency measurement tools.

---

## **Networking & Transport**

* **Initial Transport**

  * [ ] WebSocket streaming with chunked PCM.
  * [ ] Error handling for dropped connections.
* **Advanced**

  * [ ] Migrate to gRPC bidirectional streaming (LAN).
  * [ ] WebRTC for remote/cloud use.
  * [ ] Back-pressure handling under load.

---

## **Security & Privacy**

* [ ] Local-only mode (no raw audio leaves machine).
* [ ] End-to-end encryption for remote mode.
* [ ] No transcript retention by default.
* [ ] Optional consented logging for debugging.
* [ ] “Synthetic Voice” indicator in UI.
* [ ] Watermarking for synthetic audio (optional).

---

## **Documentation & Maintenance**

* **User Docs**

  * [ ] Install guide (Windows with WSL2).
  * [ ] Audio device setup wizard for VB-CABLE.
  * [ ] Troubleshooting common latency issues.
  * [ ] Discord/gaming integration guide.
* **Developer Docs**

  * [ ] Architecture overview ADR.
  * [ ] Latency targets ADR.
  * [ ] Monorepo structure ADR.
  * [ ] Runbook for local & cloud deployment.
* **Maintenance**

  * [ ] CI/CD pipeline for client + server builds.
  * [ ] Automated audio regression tests.
  * [ ] Dependency update schedule.
  * [ ] Security vulnerability scan in CI.

---

## **Testing & Quality Gates**

* **Audio Testing**

  * [ ] Loopback latency measurements (p50, p95).
  * [ ] Sine sweep and speech sample distortion checks.
* **Network Testing**

  * [ ] Simulated packet loss/jitter.
  * [ ] Stress test with multiple concurrent streams.
* **Interop Testing**

  * [ ] Discord test call.
  * [ ] Game chat (Valorant, CS\:GO, etc.).
  * [ ] OBS/NVIDIA Broadcast compatibility.

---

## **Future Enhancements**

* [ ] Smart mode: auto-switch VC ↔ ASR→TTS based on network conditions.
* [ ] Preset designer (prompt → voice style).
* [ ] MCP endpoints for automation.
* [ ] Linux/macOS desktop builds.
* [ ] Marketplace for community voice presets (with rights checks).
* [ ] Per-app routing controls.
