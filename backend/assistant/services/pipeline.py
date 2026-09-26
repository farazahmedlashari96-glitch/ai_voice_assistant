"""One conversation turn (stateless): clean text -> exit check -> LLM -> (optional) TTS.

Workflow from the project brief: text -> LLM API -> response -> TTS -> audio + text.
The conversation history is supplied by the caller (the browser keeps it).
"""
import base64
import logging
import time

from django.conf import settings

from . import audio_store, llm, tts
from .errors import NoInputError, ServiceError
from .text_processing import GOODBYE_MESSAGE, clean_user_text, is_exit_command

log = logging.getLogger(__name__)


def trim_history(history: list[dict]) -> list[dict]:
    """Keep the last N messages, always starting with a user turn."""
    trimmed = list(history)[-settings.MAX_HISTORY_MESSAGES:]
    while trimmed and trimmed[0]["role"] != "user":
        trimmed.pop(0)
    return trimmed


def process_text_turn(
    history: list[dict],
    raw_text: str,
    speak: bool = True,
    timings: dict | None = None,
) -> dict:
    started = time.perf_counter()
    timings = dict(timings or {})

    text = clean_user_text(raw_text)                       # 4. text processing
    if not text:
        raise NoInputError()

    exit_requested = is_exit_command(text)                 # 6. exit command
    if exit_requested:
        reply = GOODBYE_MESSAGE
    else:                                                  # 3. LLM API
        llm_started = time.perf_counter()
        reply = llm.generate_reply([*trim_history(history), {"role": "user", "content": text}])
        timings["llm_ms"] = round((time.perf_counter() - llm_started) * 1000)

    audio = tts_error = None
    if speak:                                              # 5. text-to-speech
        tts_started = time.perf_counter()
        try:
            wav = tts.synthesize(reply)
            audio_store.save_response(wav)
            audio = base64.b64encode(wav).decode("ascii")
        except ServiceError as exc:
            tts_error = exc.message
            log.warning("TTS failed: %s", exc.message)
        except Exception:  # never lose a good text reply because speech failed
            log.exception("Unexpected TTS failure")
            tts_error = "Speech synthesis failed."
        timings["tts_ms"] = round((time.perf_counter() - tts_started) * 1000)

    timings["total_ms"] = round((time.perf_counter() - started) * 1000 + timings.get("stt_ms", 0))
    return {
        "user_text": text,
        "reply": reply,
        "exit": exit_requested,
        "audio": audio,
        "audio_mime": "audio/wav" if audio else None,
        "tts_error": tts_error,
        "timings": timings,
    }
