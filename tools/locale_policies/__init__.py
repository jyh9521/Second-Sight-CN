"""Explicit language-policy registry; engine validation stays elsewhere."""

from .zh_sentence_endings import check_sentence_endings
from .zh_sentence_endings import analyze as analyze_zh

ANALYZERS = {'zh': analyze_zh}


def analyze_locale_text(locale, text):
    """Dispatch locale policy without putting punctuation in the game adapter."""
    analyzer = ANALYZERS.get(locale.split('-', 1)[0].casefold())
    if analyzer is None:
        raise ValueError('no sentence policy configured for locale: ' + locale)
    return analyzer(text)

POLICIES = {'zh': check_sentence_endings}


def check_locale(locale, entry):
    policy = POLICIES.get(locale.split('-', 1)[0].casefold())
    return policy(entry) if policy else []
