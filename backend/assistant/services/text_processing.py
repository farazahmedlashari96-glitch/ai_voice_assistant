"""Text clean-up for the LLM (input) and for the speaker (output)."""
import re

from django.conf import settings

GOODBYE_MESSAGE = "Goodbye! Have a great day."

EXIT_COMMANDS = {
    "exit", "quit", "stop", "goodbye", "good bye", "bye",
    "stop listening", "exit assistant", "quit assistant",
}

_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_URL = re.compile(r"https?://\S+")
_BRACKETS = re.compile(r"\[[^\]]*\]")  # Orpheus reads [text] as a vocal direction
_BULLET = re.compile(r"^\s*[-•*]\s+", re.MULTILINE)
_MARKDOWN = re.compile(r"[*`#~]+")
_SPACES = re.compile(r"\s+")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def clean_user_text(text: str) -> str:
    """Trim, collapse whitespace, capitalise and cap the length of user input."""
    text = _SPACES.sub(" ", text or "").strip()
    if not text:
        return ""
    text = text[: settings.MAX_INPUT_CHARS]
    return text[0].upper() + text[1:]


def is_exit_command(text: str) -> bool:
    """True if the whole utterance is an exit phrase ("Exit.", "please stop!")."""
    normalized = re.sub(r"[^\w\s]", "", (text or "").lower()).strip()
    if normalized.startswith("please "):
        normalized = normalized[len("please "):]
    return normalized in EXIT_COMMANDS


def clean_for_speech(text: str) -> str:
    """Remove markdown, URLs and [brackets] so the TTS does not read symbols aloud."""
    text = _CODE_BLOCK.sub(" ", text or "")
    text = _LINK.sub(r"\1", text)
    text = _URL.sub("link", text)
    text = _BRACKETS.sub(" ", text)
    text = _BULLET.sub("", text)
    text = _MARKDOWN.sub("", text)
    return _SPACES.sub(" ", text).strip()


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    ends = list(re.finditer(r"[.!?](?=\s|$)", cut))
    if ends:
        return cut[: ends[-1].end()]
    return cut.rsplit(" ", 1)[0]


def _hard_split(piece: str, limit: int) -> list[str]:
    out, current = [], ""
    for word in piece.split(" "):
        if len(word) > limit:  # a single absurdly long token
            if current:
                out.append(current)
                current = ""
            out.extend(word[i : i + limit] for i in range(0, len(word), limit))
            continue
        candidate = f"{current} {word}".strip()
        if len(candidate) <= limit:
            current = candidate
        else:
            out.append(current)
            current = word
    if current:
        out.append(current)
    return out


def split_for_tts(text: str, limit: int | None = None, max_chars: int | None = None) -> list[str]:
    """Split text into <= ``limit``-char chunks on sentence boundaries (Groq's TTS cap)."""
    limit = limit or settings.TTS_CHUNK_CHARS
    max_chars = max_chars or settings.TTS_MAX_CHARS
    text = _truncate(_SPACES.sub(" ", text or "").strip(), max_chars)

    chunks, current = [], ""
    for sentence in _SENTENCE_END.split(text):
        if len(sentence) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(_hard_split(sentence, limit))
            continue
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= limit:
            current = candidate
        else:
            chunks.append(current)
            current = sentence
    if current:
        chunks.append(current)
    return [c for c in chunks if re.search(r"\w", c)]


def make_title(text: str, limit: int = 48) -> str:
    text = _SPACES.sub(" ", text).strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
