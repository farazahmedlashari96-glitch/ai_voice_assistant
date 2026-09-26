"""JSON API used by the React frontend.

POST /api/voice/  recorded audio (WAV) -> transcript -> reply -> speech
POST /api/chat/   typed text           ->              reply -> speech
GET  /api/health/ status
"""
import functools
import json
import logging
import time

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .services import audio_store, pipeline, stt
from .services.errors import NoInputError, ServiceError

log = logging.getLogger(__name__)

_EXTENSIONS = {
    "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav",
    "audio/webm": "webm", "audio/ogg": "ogg", "audio/opus": "opus",
    "audio/mp4": "mp4", "audio/m4a": "m4a", "audio/x-m4a": "m4a",
    "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/flac": "flac",
}
_SUPPORTED_EXTENSIONS = set(_EXTENSIONS.values()) | {"mpeg", "mpga"}
_MAX_HISTORY_ITEM_CHARS = 2000


# ------------------------------------------------------------------ helpers
def _error(code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse({"error": {"code": code, "message": message}}, status=status)


def api(*methods):
    """JSON endpoint: restricts HTTP methods and converts every error to JSON."""

    def decorator(view):
        @functools.wraps(view)
        def inner(request, *args, **kwargs):
            try:
                return view(request, *args, **kwargs)
            except ServiceError as exc:
                return _error(exc.code, exc.message, exc.status)
            except Exception:
                log.exception("Unhandled error in %s", view.__name__)
                return _error("server_error", "Something went wrong on the server.", 500)

        return require_http_methods(list(methods))(inner)

    return decorator


def _bad_request(message: str) -> ServiceError:
    return ServiceError("bad_request", message, 400)


def _json_body(request) -> dict:
    try:
        data = json.loads(request.body or b"{}")
    except (ValueError, UnicodeDecodeError):
        raise _bad_request("Request body must be valid JSON.")
    if not isinstance(data, dict):
        raise _bad_request("Request body must be a JSON object.")
    return data


def _to_bool(value, default: bool = True) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_history(value) -> list[dict]:
    """Validate the [{"role", "content"}] list the browser sends (JSON string or list)."""
    if value in (None, ""):
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            raise _bad_request("'history' must be valid JSON.")
    if not isinstance(value, list):
        raise _bad_request("'history' must be a list of messages.")

    history = []
    for item in value:
        if (
            not isinstance(item, dict)
            or item.get("role") not in {"user", "assistant"}
            or not isinstance(item.get("content"), str)
        ):
            raise _bad_request("Each history item needs a 'role' (user/assistant) and text 'content'.")
        content = item["content"].strip()[:_MAX_HISTORY_ITEM_CHARS]
        if content:
            history.append({"role": item["role"], "content": content})
    return history


def _audio_extension(upload) -> str:
    """Groq decides the audio format from the file extension, so make sure it is right."""
    content_type = (upload.content_type or "").split(";")[0].strip().lower()
    if content_type in _EXTENSIONS:
        return _EXTENSIONS[content_type]
    ext = (upload.name or "").rsplit(".", 1)[-1].lower()
    return ext if ext in _SUPPORTED_EXTENSIONS else "wav"


# ------------------------------------------------------------------ endpoints
@api("GET")
def health(request):
    return JsonResponse(
        {
            "status": "ok",
            "groq_configured": bool(settings.GROQ_API_KEY),
            "response_time_target_ms": int(settings.RESPONSE_TIME_TARGET_SECONDS * 1000),
            "models": {
                "llm": settings.GROQ_LLM_MODEL,
                "stt": settings.GROQ_STT_MODEL,
                "tts": settings.GROQ_TTS_MODEL,
            },
        }
    )


@api("POST")
def chat(request):
    """Typed message -> reply (+ optional speech)."""
    data = _json_body(request)
    message = data.get("message")
    if not isinstance(message, str):
        raise _bad_request("'message' must be a string.")
    payload = pipeline.process_text_turn(
        _parse_history(data.get("history")),
        message,
        speak=_to_bool(data.get("speak"), True),
    )
    return JsonResponse(payload)


@api("POST")
def voice(request):
    """Recorded audio -> transcript -> reply (+ optional speech)."""
    upload = request.FILES.get("audio")
    if upload is None:
        raise _bad_request("No audio file was uploaded (form field 'audio').")
    if upload.size > settings.MAX_AUDIO_BYTES:
        raise ServiceError("audio_too_large", "That recording is too long. Please keep it shorter.", 413)
    if upload.size < settings.MIN_AUDIO_BYTES:
        raise NoInputError()

    history = _parse_history(request.POST.get("history"))
    audio = upload.read()
    extension = _audio_extension(upload)
    audio_store.save_recording(audio, f".{extension}")           # Phase 2

    started = time.perf_counter()
    transcript = stt.transcribe(audio, f"recording.{extension}")  # 2. speech -> text
    stt_ms = round((time.perf_counter() - started) * 1000)

    payload = pipeline.process_text_turn(
        history,
        transcript,
        speak=_to_bool(request.POST.get("speak"), True),
        timings={"stt_ms": stt_ms},
    )
    payload["transcript"] = transcript
    return JsonResponse(payload)
