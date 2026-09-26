"""Speech-to-text with Groq's hosted Whisper."""
import logging

from django.conf import settings

from . import groq_client
from .errors import UnclearAudioError

log = logging.getLogger(__name__)


def _get(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _extract_text(result) -> str:
    """Return the transcript, dropping segments Whisper itself flags as non-speech.

    Whisper tends to "hallucinate" phrases like "Thank you." on silence or noise.
    Its own rule for skipping such segments is: no_speech_prob > 0.6 and
    avg_logprob < -1.0.
    """
    segments = _get(result, "segments")
    if segments:
        kept = []
        for seg in segments:
            no_speech = _get(seg, "no_speech_prob", 0.0) or 0.0
            avg_logprob = _get(seg, "avg_logprob", 0.0) or 0.0
            if no_speech > 0.6 and avg_logprob < -1.0:
                continue
            kept.append(str(_get(seg, "text", "")).strip())
        return " ".join(t for t in kept if t).strip()
    return str(_get(result, "text", "") or "").strip()


def transcribe(audio: bytes, filename: str) -> str:
    """Transcribe recorded audio (webm/ogg/mp4/wav/mp3...) to text."""
    client = groq_client.get_client()
    kwargs = {
        "file": (filename, audio),
        "model": settings.GROQ_STT_MODEL,
        "response_format": "verbose_json",
        "temperature": 0.0,
    }
    if settings.STT_LANGUAGE:
        kwargs["language"] = settings.STT_LANGUAGE

    try:
        result = client.audio.transcriptions.create(**kwargs)
    except Exception as exc:
        raise groq_client.translate_error(exc, "transcription") from exc

    text = _extract_text(result)
    if not text:
        raise UnclearAudioError()
    log.info("Transcribed: %s", text)
    return text
