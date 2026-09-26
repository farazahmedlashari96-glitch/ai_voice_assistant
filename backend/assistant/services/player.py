"""Functional requirement 5 (terminal mode): play the spoken reply through the speakers."""
import io
import wave

import numpy as np

from .errors import AudioDeviceError
from .recorder import _missing_audio_message


def play_wav(wav_bytes: bytes) -> None:
    """Play 16-bit PCM WAV bytes and wait until playback has finished."""
    try:
        import sounddevice as sd
    except (ImportError, OSError) as exc:
        raise AudioDeviceError(_missing_audio_message(exc)) from exc

    try:
        with wave.open(io.BytesIO(wav_bytes)) as wav:
            channels, width, rate = wav.getnchannels(), wav.getsampwidth(), wav.getframerate()
            raw = wav.readframes(wav.getnframes())
    except (wave.Error, EOFError) as exc:
        raise AudioDeviceError(f"The reply audio could not be read: {exc}") from exc
    if width != 2:
        raise AudioDeviceError("Only 16-bit WAV playback is supported.")

    audio = np.frombuffer(raw, dtype="<i2").reshape(-1, channels)
    try:
        sd.play(audio, rate)
        sd.wait()
    except Exception as exc:
        raise AudioDeviceError(f"Could not play audio: {exc}") from exc
