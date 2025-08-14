import asyncio
import logging
from typing import Optional, List

import numpy as np

log = logging.getLogger("asr_tts")


def resample_linear_i16(pcm_bytes: bytes, from_sr: int, to_sr: int) -> bytes:
    if from_sr == to_sr:
        return pcm_bytes
    x = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
    n = x.size
    if n == 0:
        return pcm_bytes
    duration = n / from_sr
    m = max(1, int(round(duration * to_sr)))
    xp = np.linspace(0.0, 1.0, n)
    fp = x
    xq = np.linspace(0.0, 1.0, m)
    y = np.interp(xq, xp, fp)
    y = np.clip(np.round(y), -32768.0, 32767.0).astype(np.int16)
    return y.tobytes()


class BaseAsrEngine:
    async def start(self) -> None:
        return None

    async def feed_chunk(self, pcm_bytes_48k_mono_s16: bytes) -> Optional[str]:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class DummyAsrEngine(BaseAsrEngine):
    def __init__(self, trigger_seconds: float = 1.5, sample_rate: int = 48000) -> None:
        self.accum: List[bytes] = []
        self.trigger_samples = int(trigger_seconds * sample_rate)
        self._samples = 0

    async def feed_chunk(self, pcm_bytes_48k_mono_s16: bytes) -> Optional[str]:
        self.accum.append(pcm_bytes_48k_mono_s16)
        self._samples += len(pcm_bytes_48k_mono_s16) // 2
        if self._samples >= self.trigger_samples:
            self._samples = 0
            self.accum.clear()
            log.info("dummy asr: fired placeholder transcript")
            return "This is a placeholder transcript."
        return None


class VoskAsrEngine(BaseAsrEngine):
    def __init__(self, model_path: Optional[str], sample_rate: int = 48000) -> None:
        self.sample_rate = sample_rate
        self.model_path = model_path
        self._rec = None
        self._available = False
        # Accumulate ~50ms chunks at 16k mono for better responsiveness
        self._buf = bytearray()
        self._stride_bytes = int(0.05 * 16000 * 2)

    async def start(self) -> None:
        try:
            import vosk  # type: ignore
        except Exception as exc:
            log.warning("vosk not available: %s", exc)
            return
        if not self.model_path:
            log.warning("VOSK model path not configured; falling back to dummy ASR")
            return
        try:
            self._model = vosk.Model(self.model_path)
            self._rec = vosk.KaldiRecognizer(self._model, 16000)
            self._available = True
            log.info("VOSK ASR ready at %s", self.model_path)
        except Exception as exc:
            log.warning("failed to init vosk: %s", exc)

    async def feed_chunk(self, pcm_bytes_48k_mono_s16: bytes) -> Optional[str]:
        if not self._available or self._rec is None:
            return None
        # downsample 48k -> 16k for ASR
        pcm_16k = resample_linear_i16(pcm_bytes_48k_mono_s16, 48000, 16000)
        try:
            # Accumulate and feed in ~50ms strides
            self._buf.extend(pcm_16k)
            log.debug("vosk buf_len=%d stride=%d", len(self._buf), self._stride_bytes)
            fed = 0
            while len(self._buf) >= self._stride_bytes:
                chunk = bytes(self._buf[: self._stride_bytes])
                del self._buf[: self._stride_bytes]
                fed += len(chunk)
                ok = self._rec.AcceptWaveform(chunk)
                if ok:
                    import json
                    res = json.loads(self._rec.Result())
                    text = (res.get("text") or "").strip()
                    if text:
                        log.info("vosk full result: %s", text)
                        return text
                else:
                    # Log partial availability for debugging
                    try:
                        import json
                        part = self._rec.PartialResult()
                        ptext = (json.loads(part).get("partial") or "").strip()
                        if ptext:
                            log.info("vosk partial: %s", ptext)
                    except Exception:
                        pass
            if fed:
                log.debug("vosk fed_bytes=%d", fed)
        except Exception as exc:
            log.warning("vosk feed error: %s", exc)
        return None


class BaseTtsEngine:
    async def synthesize(self, text: str) -> bytes:
        raise NotImplementedError


class EdgeTtsEngine(BaseTtsEngine):
    def __init__(self, voice: str = "en-US-AriaNeural") -> None:
        self.voice = voice

    async def synthesize(self, text: str) -> bytes:
        # Aggregate PCM by configuring output_format on the communicator ctor (compatible across edge-tts versions)
        import edge_tts  # type: ignore
        communicate = edge_tts.Communicate(text, self.voice, output_format="raw-24khz-16bit-mono-pcm")
        pcm = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                pcm.extend(chunk["data"])  # 24k PCM
        return bytes(pcm)

    async def stream(self, text: str):
        # Streaming PCM chunks
        import edge_tts  # type: ignore
        communicate = edge_tts.Communicate(text, self.voice, output_format="raw-24khz-16bit-mono-pcm")
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]


class AsrTtsSession:
    def __init__(self, sample_rate: int, frame_size: int, asr: BaseAsrEngine, tts: BaseTtsEngine) -> None:
        self.sample_rate = sample_rate
        self.frame_size = frame_size
        self.asr = asr
        self.tts = tts
        self._frame_bytes = frame_size * 2
        # Streaming TTS queue and task
        self._tts_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=64)
        self._tts_task: Optional[asyncio.Task] = None
        # Buffer for assembling exact frame-sized outputs
        self._pending_buf = bytearray()
        # ASR partial handling
        self._last_partial: str = ""

    async def start(self) -> None:
        await self.asr.start()

    async def _run_tts_stream(self, text: str) -> None:
        log.info("TTS start: %s", text)
        try:
            # Prefer streaming if engine supports it
            if hasattr(self.tts, "stream"):
                async for chunk24 in self.tts.stream(text):  # type: ignore[attr-defined]
                    data = resample_linear_i16(chunk24, 24000, self.sample_rate)
                    try:
                        self._tts_queue.put_nowait(data)
                    except asyncio.QueueFull:
                        log.warning("tts queue full; dropping chunk")
            else:
                pcm24 = await self.tts.synthesize(text)
                data = resample_linear_i16(pcm24, 24000, self.sample_rate)
                for i in range(0, len(data), self._frame_bytes * 4):
                    await self._tts_queue.put(data[i:i + self._frame_bytes * 4])
        except Exception as exc:
            log.warning("TTS stream failed: %s", exc)
        finally:
            log.info("TTS done")

    async def _maybe_start_tts(self, text: str) -> None:
        # Stop previous task if still running
        if self._tts_task and not self._tts_task.done():
            self._tts_task.cancel()
        self._tts_task = asyncio.create_task(self._run_tts_stream(text))

    async def _drain_queue_to_frame(self) -> Optional[bytes]:
        # Fill pending_buf up to one frame and return it if complete
        try:
            while len(self._pending_buf) < self._frame_bytes:
                chunk = self._tts_queue.get_nowait()
                self._pending_buf.extend(chunk)
        except asyncio.QueueEmpty:
            pass
        if len(self._pending_buf) >= self._frame_bytes:
            out = bytes(self._pending_buf[: self._frame_bytes])
            del self._pending_buf[: self._frame_bytes]
            return out
        return None

    async def feed_and_maybe_generate(self, pcm_frame_mono_s16: bytes) -> Optional[bytes]:
        # If TTS queue already has audio, serve it immediately
        out = await self._drain_queue_to_frame()
        if out is not None:
            return out

        # Otherwise, feed ASR and see if we got a transcript
        transcript = await self.asr.feed_chunk(pcm_frame_mono_s16)
        if not transcript and isinstance(self.asr, VoskAsrEngine):  # type: ignore[name-defined]
            # Try partial for lower latency
            try:
                import json
                part = self.asr._rec.PartialResult() if getattr(self.asr, "_rec", None) else None  # type: ignore[attr-defined]
                if part:
                    ptext = (json.loads(part).get("partial") or "").strip()
                    if ptext and ptext != self._last_partial and len(ptext) >= 8:
                        transcript = ptext
                        self._last_partial = ptext
            except Exception:
                pass

        if transcript:
            log.info("ASR transcript: %s", transcript)
            await self._maybe_start_tts(transcript)
            # Try to serve first frame if any audio has arrived already
            return await self._drain_queue_to_frame()

        return None


