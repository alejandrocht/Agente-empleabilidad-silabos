"""Deterministic identity for every source-derived identifier.

The normalizer derives most of its identifiers by hashing normalized parts.
That logic had grown seven private copies across the package, and two of them
`clasificacion._grupo` and `empleabilidad.pipeline._hash_id` skipped the
normalization step entirely, so the same logical input produced a different
identifier depending on which module computed it.

This module is the single implementation. `normalize` folds a value to its
comparison key and `hashed` builds `<prefix>_<16 hex chars>` over the
normalized parts.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

__all__ = ["hashed", "normalize"]

DIGEST_LENGTH = 16

# Characters that survive normalization because they distinguish real tools:
# `C++` and `C#` must not fold into the same key.
_SIGNIFICANT = re.compile(r"[^a-z0-9#+.]")
_WHITESPACE = re.compile(r"\s+")


def normalize(value: object) -> str:
    """Fold a value to its comparison key.

    NFKD, lowercase, strip diacritics, replace everything that is not a
    letter, digit or the significant ``# + .`` characters with a space, then
    collapse runs of whitespace. ``MS Excel``, ``ms  excel`` and ``MS Éxcel``
    therefore share one key, while ``C++`` and ``C#`` stay distinct.

    A falsy value folds to the empty string. This matches the historical
    `clave_concepto` contract that callers already depend on for comparisons,
    and it only differs from a bare `str(value)` for inputs that never reach
    an identifier: `None` and `0`.
    """

    folded = unicodedata.normalize("NFKD", str(value if value else "")).lower()
    without_diacritics = "".join(char for char in folded if not unicodedata.combining(char))
    return _WHITESPACE.sub(" ", _SIGNIFICANT.sub(" ", without_diacritics)).strip()


def hashed(prefix: str, *parts: str) -> str:
    """Build ``<prefix>_<16 hex chars>`` over the normalized parts.

    Part order is significant, and the prefix participates only in the label,
    never in the digest: `hashed("CUR", code)` and `hashed("SIL", code)` share
    a digest and differ only by prefix. That is intentional — a course and its
    syllabus are keyed by the same code.
    """

    payload = "|".join(normalize(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:DIGEST_LENGTH]
    return f"{prefix}_{digest}"
