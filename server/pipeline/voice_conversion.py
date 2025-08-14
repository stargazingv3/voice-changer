import numpy as np


class PitchShifter:
    """
    Low-latency time-domain pitch shifter using fractional resampling with a persistent buffer.
    Keeps output frame length equal to input frame length. For semitones > 0, pitch goes up.
    """

    def __init__(self, sample_rate: int, semitones: float = 4.0) -> None:
        self.sample_rate = int(sample_rate)
        self.semitones = float(semitones)
        # Read step in source samples per one output sample
        self.factor = float(2.0 ** (self.semitones / 12.0))
        # Internal mono buffer and fractional read phase
        self._buf = np.zeros(0, dtype=np.float32)
        self._phase = 0.0

    def _append(self, x_f32: np.ndarray) -> None:
        if self._buf.size == 0:
            self._buf = x_f32.copy()
        else:
            self._buf = np.concatenate([self._buf, x_f32])

    def _synthesize(self, out_len: int) -> np.ndarray:
        """Synthesize out_len samples by sampling _buf at fractional positions."""
        y = np.zeros(out_len, dtype=np.float32)
        max_idx = max(0, self._buf.size - 1)
        if max_idx == 0:
            return y
        for i in range(out_len):
            idx = self._phase
            if idx >= max_idx:
                # Not enough source; hold last sample
                y[i:] = self._buf[max_idx]
                self._phase += self.factor * (out_len - i)
                break
            i0 = int(idx)
            i1 = min(i0 + 1, max_idx)
            frac = float(idx - i0)
            s = (1.0 - frac) * self._buf[i0] + frac * self._buf[i1]
            y[i] = s
            self._phase += self.factor

        # Drop consumed integer part from buffer to keep it bounded
        consumed = int(self._phase)
        if consumed > 0:
            self._buf = self._buf[consumed:]
            self._phase -= consumed
        return y

    def process_frame_int16_mono(self, pcm_bytes: bytes) -> bytes:
        x_i16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        n = x_i16.size
        if n == 0:
            return pcm_bytes
        x_f32 = x_i16.astype(np.float32)
        self._append(x_f32)
        y = self._synthesize(n)
        y = np.clip(np.round(y), -32768.0, 32767.0).astype(np.int16)
        return y.tobytes()

    def process(self, pcm_bytes: bytes, channels: int) -> bytes:
        if channels == 1:
            return self.process_frame_int16_mono(pcm_bytes)
        # For multi-channel, process by downmixing to mono and duplicating back
        x = np.frombuffer(pcm_bytes, dtype=np.int16)
        if x.size == 0:
            return pcm_bytes
        x = x.reshape(-1, channels)
        mono = x.mean(axis=1).astype(np.int16)
        y = self.process_frame_int16_mono(mono.tobytes())
        y = np.frombuffer(y, dtype=np.int16)
        y_stacked = np.repeat(y[:, None], channels, axis=1).reshape(-1)
        return y_stacked.astype(np.int16).tobytes()


