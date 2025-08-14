import asyncio
import json
import time
import logging
import os
from typing import Optional
import numpy as np

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from server.pipeline.voice_conversion import PitchShifter
from server.pipeline.asr_tts import AsrTtsSession, DummyAsrEngine, VoskAsrEngine, EdgeTtsEngine


router = APIRouter()


class StreamSession:
    def __init__(self) -> None:
        self.sample_rate: int = 48000
        self.channels: int = 1
        self.sample_format: str = "S16LE"
        self.frame_size: int = 480  # samples per channel per frame (10ms @ 48kHz)
        self.bytes_per_sample: int = 2  # S16LE
        self.start_monotonic: float = time.monotonic()
        self.total_frames_received: int = 0
        self.total_bytes_received: int = 0
        self.debug_logged_frames: int = 0

    @property
    def frame_bytes(self) -> int:
        return self.frame_size * self.channels * self.bytes_per_sample


@router.websocket("/stream/audio")
async def stream_audio(websocket: WebSocket) -> None:
    await websocket.accept()

    session: Optional[StreamSession] = None
    stats_interval_seconds = 1.0
    last_stats_time = time.monotonic()
    log = logging.getLogger("vc")

    try:
        # Expect an init JSON text message first
        init_msg = await websocket.receive_text()
        try:
            init = json.loads(init_msg)
        except json.JSONDecodeError:
            await websocket.send_text(json.dumps({"type": "error", "message": "invalid init json"}))
            await websocket.close()
            return

        session = StreamSession()
        session.sample_rate = int(init.get("sampleRate", session.sample_rate))
        session.channels = int(init.get("channels", session.channels))
        session.sample_format = str(init.get("format", session.sample_format))
        session.frame_size = int(init.get("frameSize", session.frame_size))

        # Defaults from environment (allow container config without client changes)
        env_mode = os.getenv("VC_MODE", "vc")
        env_semitones = float(os.getenv("VC_SEMITONES", "6"))
        env_asr = os.getenv("VC_ASR", "dummy")
        env_voice = os.getenv("VC_TTS_VOICE", "en-US-AriaNeural")
        env_vosk_path = os.getenv("VOSK_MODEL_PATH")

        # Mode selection: "vc" or "asr_tts"
        mode = str(init.get("mode", env_mode))
        vc = None
        asr_tts: Optional[AsrTtsSession] = None
        if mode == "asr_tts":
            asr_backend = str(init.get("asr", env_asr))
            vosk_model = init.get("voskModelPath", env_vosk_path)
            if asr_backend == "vosk":
                asr = VoskAsrEngine(model_path=vosk_model, sample_rate=session.sample_rate)
            else:
                asr = DummyAsrEngine(sample_rate=session.sample_rate)
            tts_voice = str(init.get("voice", env_voice))
            tts = EdgeTtsEngine(voice=tts_voice)
            asr_tts = AsrTtsSession(session.sample_rate, session.frame_size, asr, tts)
            await asr_tts.start()
        else:
            # Initialize low-latency voice conversion (simple pitch shift for MVP)
            semitones = float(init.get("semitones", env_semitones))
            vc = PitchShifter(sample_rate=session.sample_rate, semitones=semitones)

        if mode == "asr_tts":
            log.info(
                "ws init: mode=asr_tts sr=%s ch=%s fmt=%s frame=%s asr=%s vosk_path=%s voice=%s",
                session.sample_rate,
                session.channels,
                session.sample_format,
                session.frame_size,
                asr_backend,
                vosk_model,
                tts_voice,
            )
        else:
            log.info(
                "ws init: mode=vc sr=%s ch=%s fmt=%s frame=%s semitones=%.2f",
                session.sample_rate,
                session.channels,
                session.sample_format,
                session.frame_size,
                semitones,
            )

        await websocket.send_text(
            json.dumps(
                {
                    "type": "ready",
                    "sampleRate": session.sample_rate,
                    "channels": session.channels,
                    "format": session.sample_format,
                    "frameSize": session.frame_size,
                }
            )
        )

        # Main receive/echo loop
        while True:
            message = await websocket.receive()

            if "bytes" in message and message["bytes"] is not None:
                data = message["bytes"]
                session.total_bytes_received += len(data)
                session.total_frames_received += 1

                # Apply selected mode
                try:
                    if asr_tts is not None:
                        # Stream mono frames to ASR/TTS and return TTS audio when available; otherwise return silence
                        x = np.frombuffer(data, dtype=np.int16)
                        if session.channels > 1:
                            x = x.reshape(-1, session.channels).mean(axis=1).astype(np.int16)
                        out = await asr_tts.feed_and_maybe_generate(x.tobytes())
                        # Failsafe: output only transformed audio. If not ready yet, output silence.
                        processed = out if out is not None else (b"\x00\x00" * session.frame_size)
                    else:
                        processed = vc.process(data, session.channels) if vc is not None else data
                except Exception as exc:
                    log.exception("process error: %s", exc)
                    processed = data

                # Debug: log first few frames, then every 100th frame
                if session.debug_logged_frames < 10 or (session.total_frames_received % 100 == 0):
                    try:
                        x = np.frombuffer(data, dtype=np.int16)
                        y = np.frombuffer(processed, dtype=np.int16)
                        # Protect against mismatched lengths
                        n = min(x.size, y.size)
                        if n > 0:
                            diff = (y[:n].astype(np.int32) - x[:n].astype(np.int32))
                            rms_in = float(np.sqrt(np.mean((x[:n].astype(np.float32)) ** 2)))
                            rms_out = float(np.sqrt(np.mean((y[:n].astype(np.float32)) ** 2)))
                            rms_diff = float(np.sqrt(np.mean(diff.astype(np.float32) ** 2)))
                            if asr_tts is not None and out is None:
                                log.info(
                                    "frame=%d bytes_in=%d bytes_out=%d rms_in=%.1f rms_out=%.1f rms_diff=%.1f status=waiting_tts",
                                    session.total_frames_received,
                                    len(data),
                                    len(processed),
                                    rms_in,
                                    rms_out,
                                    rms_diff,
                                )
                            else:
                                log.info(
                                    "frame=%d bytes_in=%d bytes_out=%d rms_in=%.1f rms_out=%.1f rms_diff=%.1f first3_in=%s first3_out=%s",
                                    session.total_frames_received,
                                    len(data),
                                    len(processed),
                                    rms_in,
                                    rms_out,
                                    rms_diff,
                                    x[:3].tolist(),
                                    y[:3].tolist(),
                                )
                        else:
                            log.info(
                                "frame=%d empty frame bytes_in=%d",
                                session.total_frames_received,
                                len(data),
                            )
                    except Exception as exc:
                        log.warning("debug metrics failed: %s", exc)
                    finally:
                        session.debug_logged_frames += 1

                await websocket.send_bytes(processed)

            elif "text" in message and message["text"] is not None:
                # Could be control messages later; for now, ignore non-init texts
                pass

            now = time.monotonic()
            if now - last_stats_time >= stats_interval_seconds:
                elapsed = now - session.start_monotonic
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "stats",
                            "elapsedSec": round(elapsed, 3),
                            "frames": session.total_frames_received,
                            "bytes": session.total_bytes_received,
                        }
                    )
                )
                last_stats_time = now

            # Yield to event loop to avoid hogging
            await asyncio.sleep(0)

    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass


