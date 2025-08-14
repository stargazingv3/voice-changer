**Date:** 2025-08-13  
**Status:** Accepted  

**Context:**  
User experience depends on keeping perceived latency low for real-time use.

**Decision:**  
Latency budgets:
- **VC (low-latency)**: 40–80 ms end-to-end
  - Capture + DSP: 5–15 ms
  - VC model + vocoder: 20–50 ms
  - Network (local): 5–15 ms
- **ASR→TTS (max privacy)**: 150–300 ms acceptable
  - Capture + DSP: 5–15 ms
  - ASR streaming: 50–100 ms
  - TTS synthesis: 50–100 ms
  - Network: 10–20 ms

**Consequences:**  
- Influences choice of models, chunk sizes, and frame hops.
- Informs testing and p95 latency monitoring in production.
