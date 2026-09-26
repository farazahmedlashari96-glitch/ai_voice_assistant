"""Evaluation metrics (Phase 8)."""
import re


def normalize_words(text: str) -> list[str]:
    """Lower-case words without punctuation, so 'Hello, World!' == 'hello world'."""
    return re.findall(r"[\w']+", (text or "").lower())


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Word Error Rate = (substitutions + deletions + insertions) / reference words."""
    ref, hyp = normalize_words(reference), normalize_words(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, ref_word in enumerate(ref, start=1):
        current = [i]
        for j, hyp_word in enumerate(hyp, start=1):
            cost = 0 if ref_word == hyp_word else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1] / len(ref)
