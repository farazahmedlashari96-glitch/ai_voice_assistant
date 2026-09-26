"""A stand-in for the Groq SDK client so tests need no network or API key."""
import io
import struct
import wave
from types import SimpleNamespace


def make_wav(seconds: float = 0.05, rate: int = 24000, unknown_size: bool = False) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x01\x00" * int(seconds * rate))
    data = bytearray(buffer.getvalue())
    if unknown_size:  # mimic a streamed WAV whose length is not known up front
        data[4:8] = struct.pack("<I", 0xFFFFFFFF)
        data[data.index(b"data") + 4 : data.index(b"data") + 8] = struct.pack("<I", 0xFFFFFFFF)
    return bytes(data)


class FakeBinaryResponse:
    def __init__(self, data: bytes):
        self._data = data

    def read(self) -> bytes:
        return self._data


class FakeGroq:
    def __init__(self, transcript="What is the capital of France?", reply="Paris is the capital of France.",
                 segments="auto", llm_errors=None, tts_error=None):
        self.transcript = transcript
        self.reply = reply
        self.segments = segments
        self.llm_errors = llm_errors or {}   # {model_name: exception to raise}
        self.tts_error = tts_error
        self.stt_calls, self.chat_calls, self.tts_calls = [], [], []

        self.audio = SimpleNamespace(
            transcriptions=SimpleNamespace(create=self._stt),
            speech=SimpleNamespace(create=self._tts),
        )
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat))

    def _stt(self, **kwargs):
        self.stt_calls.append(kwargs)
        segments = self.segments
        if segments == "auto":
            segments = [{"text": self.transcript, "no_speech_prob": 0.01, "avg_logprob": -0.2}] if self.transcript else []
        return SimpleNamespace(text=self.transcript, segments=segments)

    def _chat(self, **kwargs):
        self.chat_calls.append(kwargs)
        error = self.llm_errors.get(kwargs["model"])
        if error:
            raise error
        message = SimpleNamespace(content=self.reply)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    def _tts(self, **kwargs):
        self.tts_calls.append(kwargs)
        if self.tts_error:
            raise self.tts_error
        return FakeBinaryResponse(make_wav())
