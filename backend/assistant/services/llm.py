"""Chat completion with Groq-hosted LLMs (with an automatic fallback model)."""
import logging
import re

from django.conf import settings

from . import groq_client
from .errors import ServiceError

log = logging.getLogger(__name__)

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_FALLBACK_CODES = {"model_unavailable", "rate_limited"}


def generate_reply(messages: list[dict]) -> str:
    """``messages`` is the chat history: [{"role": "user"|"assistant", "content": str}, ...]."""
    client = groq_client.get_client()

    models = [settings.GROQ_LLM_MODEL]
    fallback = settings.GROQ_LLM_FALLBACK_MODEL
    if fallback and fallback not in models:
        models.append(fallback)

    for index, model in enumerate(models):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": settings.SYSTEM_PROMPT}, *messages],
                max_completion_tokens=settings.LLM_MAX_TOKENS,
                temperature=0.6,
            )
            text = _THINK.sub("", response.choices[0].message.content or "").strip()
            if not text:
                raise ServiceError("empty_reply", "The AI returned an empty response.", 502)
            log.info("LLM (%s) reply: %s", model, text)
            return text
        except Exception as exc:
            error = groq_client.translate_error(exc, "language model")
            if error.code in _FALLBACK_CODES and index < len(models) - 1:
                log.warning("Model %s failed (%s); trying %s", model, error.code, models[index + 1])
                continue
            raise error from exc

    raise ServiceError("upstream_error", "No language model is configured.", 500)  # pragma: no cover
