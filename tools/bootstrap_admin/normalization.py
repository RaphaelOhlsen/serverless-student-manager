import re
import unicodedata

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_name(full_name: str) -> str:
    normalized = unicodedata.normalize("NFKC", full_name)
    normalized = normalized.strip()
    normalized = _WHITESPACE_RE.sub(" ", normalized)

    return normalized.casefold()
