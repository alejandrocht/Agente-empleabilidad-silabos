"""Shared detection of explicit requests for canonical identifiers."""

from __future__ import annotations

import re
import unicodedata


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()


def requests_identifier(question: str) -> bool:
    """Return true only when ID is used as a requested field, not as a proper name."""
    normalized = _normalize(question)
    if "identificador" in normalized:
        return True
    descriptor = (
        r"(?:exactos?|canonicos?|correspondientes?|internos?|unicos?|oficiales?)"
    )
    requested_field = re.search(
        rf"\bids?\b(?:\s+{descriptor})*"
        r"(?=\s*(?:de(?:l|\s+la|\s+los|\s+las)?|para)\b|\s*[?¿.,!]*$)",
        normalized,
    )
    relational_question = re.search(
        r"\bids?\b\s+(?:corresponde|pertenece)\s+a\b", normalized
    )
    return bool(requested_field or relational_question)
