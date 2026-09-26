"""Functional requirement 1 (terminal mode, Python): capture the microphone as a WAV file.

Basic noise and pause handling: the background level is measured during the first
0.4 s so the speech threshold adapts to the room; recording stops after a pause once
speech was heard, and gives up if nobody speaks. ``sounddevice`` is imported lazily,
so the web app works without it.
"""
import io
import logging
import wave

import numpy as np
from django.conf import settings

from .errors import AudioDeviceError, NoInputError, ServiceError

log = logging.getLogger(__name__)

BLOCK_SECONDS = 0.1
CALIBRATION_SECONDS = 0.4
PRE_ROLL_BLOCKS = 4                       # keep a little audio from before speech starts
MIN_THRESHOLD, MAX_THRESHOLD = 0.02, 0.06  # on a 0..1 scale (fraction of full volume)


def list_input_devices() -> str:
    """Human-readable list of audio devices (python manage.py talk --list-devices)."""
    try:
        import sounddevice as sd
        return str(sd.query_devices())
    except (ImportError, OSError) as exc:
        raise AudioDeviceError(_missing_audio_message(exc)) from exc


def _missing_audio_message(exc: Exception) -> str:
    return (
        "Audio support is unavailable. Install it with 'pip install sounddevice numpy' "
        f"(Linux also needs: sudo apt install libportaudio2). Details: {exc}"
    )


def encode_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    """Mono 16-bit PCM WAV file as bytes."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(np.asarray(samples).astype("<i2").tobytes())
    return buffer.getvalue()


class MicrophoneRecorder:
    def __init__(
        self,
        sample_rate: int | None = None,
        silence_seconds: float | None = None,
        no_speech_seconds: float | None = None,
        max_seconds: float | None = None,
        device=None,
        stream_factory=None,
    ):
        self.sample_rate = sample_rate or settings.MIC_SAMPLE_RATE
        self.silence_seconds = silence_seconds or settings.MIC_SILENCE_SECONDS
        self.no_speech_seconds = no_speech_seconds or settings.MIC_NO_SPEECH_SECONDS
        self.max_seconds = max_seconds or settings.MIC_MAX_SECONDS
        self.device = device if device is not None else settings.MIC_DEVICE
        self._stream_factory = stream_factory  # tests inject a fake microphone here

    def _open_stream(self):
        if self._stream_factory:
            return self._stream_factory()
        try:
            import sounddevice as sd
        except (ImportError, OSError) as exc:
            raise AudioDeviceError(_missing_audio_message(exc)) from exc
        return sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="int16",
            blocksize=int(self.sample_rate * BLOCK_SECONDS),
            device=self.device,
        )

    def record(self) -> bytes:
        """Record one utterance and return it as WAV bytes.

        Raises NoInputError if nobody speaks, AudioDeviceError if the microphone fails.
        """
        block_frames = int(self.sample_rate * BLOCK_SECONDS)
        max_blocks = int(self.max_seconds / BLOCK_SECONDS)
        max_silent = max(1, round(self.silence_seconds / BLOCK_SECONDS))
        wait_blocks = round(self.no_speech_seconds / BLOCK_SECONDS)
        calibration_blocks = round(CALIBRATION_SECONDS / BLOCK_SECONDS)

        blocks: list[np.ndarray] = []
        noise: list[float] = []
        threshold = MIN_THRESHOLD
        heard = False
        silent = 0

        try:
            with self._open_stream() as stream:
                for index in range(max_blocks):
                    data, _overflowed = stream.read(block_frames)
                    block = np.asarray(data).reshape(-1)
                    blocks.append(block.copy())
                    rms = float(np.sqrt(np.mean((block.astype(np.float32) / 32768.0) ** 2)))

                    if index < calibration_blocks:  # measure the room's background noise
                        noise.append(rms)
                        threshold = min(MAX_THRESHOLD, max(MIN_THRESHOLD, float(np.mean(noise)) * 2.5))
                        continue

                    if rms > threshold:
                        heard, silent = True, 0
                    elif heard:
                        silent += 1

                    if heard:
                        if silent >= max_silent:
                            break  # the speaker paused: utterance finished
                    else:
                        if index + 1 >= wait_blocks:
                            raise NoInputError()
                        blocks = blocks[-PRE_ROLL_BLOCKS:]
        except ServiceError:
            raise
        except Exception as exc:
            raise AudioDeviceError(f"Microphone problem: {exc}") from exc

        if not heard:
            raise NoInputError()
        return encode_wav(np.concatenate(blocks), self.sample_rate)
