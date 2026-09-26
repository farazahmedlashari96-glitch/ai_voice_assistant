"""Text-to-speech with Groq (Orpheus).

Orpheus accepts at most 200 characters per request, so a reply is split into
sentence-sized chunks, synthesized in parallel and stitched into a single WAV.
"""
import logging
import struct
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings

from . import groq_client
from .errors import ServiceError
from .text_processing import clean_for_speech, split_for_tts

log = logging.getLogger(__name__)

_UNKNOWN_SIZE = 0xFFFFFFFF


# ------------------------------------------------------------------ WAV helpers
def _invalid_audio() -> ServiceError:
    return ServiceError("tts_error", "The speech service returned invalid audio.", 502)


def _parse_wav(data: bytes) -> tuple[tuple[int, int, int], bytes]:
    """Return ((channels, sample_rate, bits), pcm_bytes).

    Tolerates streamed WAVs whose header declares an unknown (0xFFFFFFFF) data length.
    """
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise _invalid_audio()

    fmt = pcm = None
    offset = 12
    while offset + 8 <= len(data):
        chunk_id = data[offset : offset + 4]
        size = struct.unpack("<I", data[offset + 4 : offset + 8])[0]
        body = offset + 8
        if chunk_id == b"fmt ":
            _, channels, rate, _, _, bits = struct.unpack("<HHIIHH", data[body : body + 16])
            fmt = (channels, rate, bits)
        elif chunk_id == b"data":
            end = body + size
            pcm = data[body:] if size == _UNKNOWN_SIZE or end > len(data) else data[body:end]
            break
        offset = body + size + (size & 1)

    if fmt is None or pcm is None:
        raise _invalid_audio()
    return fmt, pcm


def _build_wav(fmt: tuple[int, int, int], pcm: bytes) -> bytes:
    channels, rate, bits = fmt
    block_align = channels * bits // 8
    header = (
        b"RIFF"
        + struct.pack("<I", 36 + len(pcm))
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * block_align, block_align, bits)
        + b"data"
        + struct.pack("<I", len(pcm))
    )
    return header + pcm


def merge_wavs(parts: list[bytes]) -> bytes:
    """Concatenate WAV files that share the same format into one well-formed WAV."""
    fmt = None
    pcm_parts = []
    for part in parts:
        part_fmt, pcm = _parse_wav(part)
        if fmt is None:
            fmt = part_fmt
        elif part_fmt != fmt:
            raise _invalid_audio()
        pcm_parts.append(pcm)
    if fmt is None:
        raise _invalid_audio()
    return _build_wav(fmt, b"".join(pcm_parts))


def _read_bytes(response) -> bytes:
    if hasattr(response, "read"):
        return response.read()
    return response.content


# ------------------------------------------------------------------ public API
def synthesize(text: str) -> bytes:
    """Return WAV bytes speaking ``text``."""
    chunks = split_for_tts(clean_for_speech(text))
    if not chunks:
        raise ServiceError("tts_error", "There is nothing to speak.", 422)

    client = groq_client.get_client()

    def render(chunk: str) -> bytes:
        try:
            response = client.audio.speech.create(
                model=settings.GROQ_TTS_MODEL,
                voice=settings.GROQ_TTS_VOICE,
                input=chunk,
                response_format="wav",
            )
            return _read_bytes(response)
        except Exception as exc:
            raise groq_client.translate_error(exc, "speech") from exc

    if len(chunks) == 1:
        parts = [render(chunks[0])]
    else:
        with ThreadPoolExecutor(max_workers=min(4, len(chunks))) as pool:
            parts = list(pool.map(render, chunks))  # map() keeps the original order
    return merge_wavs(parts)
