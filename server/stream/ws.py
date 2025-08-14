import asyncio
import json
import time
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect


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

    @property
    def frame_bytes(self) -> int:
        return self.frame_size * self.channels * self.bytes_per_sample


@router.websocket("/stream/audio")
async def stream_audio(websocket: WebSocket) -> None:
    await websocket.accept()

    session: Optional[StreamSession] = None
    stats_interval_seconds = 1.0
    last_stats_time = time.monotonic()

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

                # Echo raw PCM back immediately (pass-through)
                await websocket.send_bytes(data)

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


