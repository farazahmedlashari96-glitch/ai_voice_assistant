"""Django settings. Secrets and options come from environment variables / backend/.env.

The API is stateless (the browser sends the conversation history with each request),
so there is no database and nothing to migrate.
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env_list(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DEBUG = _env_bool("DJANGO_DEBUG", True)
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-insecure-key-change-me")
if not DEBUG and SECRET_KEY.startswith("dev-only"):
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY when DJANGO_DEBUG is off.")

ALLOWED_HOSTS = _env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = ["corsheaders", "assistant"]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {}  # stateless API: no database

USE_TZ = True
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# The React dev server runs on another origin; allow it to call the API.
CORS_ALLOWED_ORIGINS = _env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)

# ----------------------------------------------------------------- Groq (one API key)
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_LLM_MODEL = os.getenv("GROQ_LLM_MODEL", "llama-3.3-70b-versatile").strip()
GROQ_LLM_FALLBACK_MODEL = os.getenv("GROQ_LLM_FALLBACK_MODEL", "llama-3.1-8b-instant").strip()
GROQ_STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo").strip()
GROQ_TTS_MODEL = os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english").strip()
GROQ_TTS_VOICE = os.getenv("GROQ_TTS_VOICE", "autumn").strip()
GROQ_TIMEOUT = _env_float("GROQ_TIMEOUT", 25.0)

# ----------------------------------------------------------------- assistant behaviour
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "").strip()   # "" = auto-detect
LLM_MAX_TOKENS = _env_int("LLM_MAX_TOKENS", 300)
MAX_HISTORY_MESSAGES = _env_int("MAX_HISTORY_MESSAGES", 12)
MAX_INPUT_CHARS = 1000
RESPONSE_TIME_TARGET_SECONDS = 5.0   # project requirement: reply within 2-5 seconds

# Phase 2: audio files are stored (WAV recordings in, spoken replies out) and pruned.
AUDIO_DIR = Path(os.getenv("AUDIO_DIR", BASE_DIR / "audio_files"))
STORE_AUDIO = _env_bool("STORE_AUDIO", True)
KEEP_LAST_FILES = _env_int("KEEP_LAST_FILES", 20)

# Terminal mode (python manage.py talk): microphone recording
MIC_SAMPLE_RATE = 16000                                  # Hz, ideal for speech recognition
MIC_SILENCE_SECONDS = _env_float("MIC_SILENCE_SECONDS", 1.4)      # pause that ends an utterance
MIC_NO_SPEECH_SECONDS = _env_float("MIC_NO_SPEECH_SECONDS", 8.0)  # give up if nobody speaks
MIC_MAX_SECONDS = _env_float("MIC_MAX_SECONDS", 30.0)
MIC_DEVICE = os.getenv("MIC_DEVICE", "").strip() or None          # sounddevice device id/name

MAX_AUDIO_BYTES = _env_int("MAX_AUDIO_MB", 10) * 1024 * 1024
MIN_AUDIO_BYTES = 8000   # < ~0.25 s of 16 kHz WAV: treat as "no input"

# Groq's Orpheus TTS accepts at most 200 characters per request, so replies are
# split into chunks. Only the first TTS_MAX_CHARS characters of a reply are spoken.
TTS_CHUNK_CHARS = 190
TTS_MAX_CHARS = 600

SYSTEM_PROMPT = (
    "You are a friendly AI voice assistant. Your replies are read aloud, so: "
    "answer in one to three short, conversational sentences unless the user asks "
    "for more detail; use plain text only (no markdown, lists, emojis, code blocks "
    "or square brackets); if you are unsure, say so briefly."
)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "loggers": {"assistant": {"handlers": ["console"], "level": "INFO"}},
}
