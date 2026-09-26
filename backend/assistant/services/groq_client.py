"""One shared Groq client, plus translation of SDK errors into friendly ServiceErrors."""
import logging
import threading

import groq
from django.conf import settings

from .errors import ServiceError

log = logging.getLogger(__name__)

_client = None
_lock = threading.Lock()


def get_client():
    """Return the shared Groq client (created on first use)."""
    global _client
    if not settings.GROQ_API_KEY:
        raise ServiceError(
            "config_error",
            "GROQ_API_KEY is not set. Add it to backend/.env and restart the server.",
            503,
        )
    with _lock:
        if _client is None:
            _client = groq.Groq(
                api_key=settings.GROQ_API_KEY,
                timeout=settings.GROQ_TIMEOUT,
                max_retries=2,
            )
    return _client


def translate_error(exc: Exception, stage: str) -> ServiceError:
    """Map any exception raised while calling Groq to a ServiceError."""
    if isinstance(exc, ServiceError):
        return exc

    log.warning("Groq %s call failed: %s: %s", stage, type(exc).__name__, exc)

    if isinstance(exc, groq.AuthenticationError):
        return ServiceError(
            "auth_error", "Groq rejected the API key. Check GROQ_API_KEY in backend/.env.", 502
        )
    if isinstance(exc, groq.RateLimitError):
        return ServiceError(
            "rate_limited", "Groq's rate limit was reached. Please wait a moment and try again.", 429
        )
    if isinstance(exc, groq.APITimeoutError):
        return ServiceError("upstream_timeout", f"Groq took too long to respond ({stage}).", 504)
    if isinstance(exc, groq.APIConnectionError):
        return ServiceError(
            "upstream_unavailable",
            "Could not reach Groq. Check the server's internet connection.",
            503,
        )
    if isinstance(exc, (groq.NotFoundError, groq.PermissionDeniedError)):
        return ServiceError(
            "model_unavailable",
            f"Groq denied access to, or could not find, the model used for {stage}. Check the "
            "model name in backend/.env and the Model Permissions page in the Groq console.",
            502,
        )
    if isinstance(exc, groq.APIStatusError):
        return ServiceError(
            "upstream_error", f"Groq returned an error during {stage} ({exc.status_code}).", 502
        )
    return ServiceError("upstream_error", f"Unexpected error during {stage}.", 502)
