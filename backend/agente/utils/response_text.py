"""Normalize public text returned by LangChain/OpenAI Responses API messages."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast


def normalize_response_text(content: object) -> str:
    """Extract recognized text blocks without coercing arbitrary objects to strings."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, Mapping):
        block = cast(Mapping[str, Any], content)
        block_type = block.get("type")
        if block_type in {"text", "output_text"}:
            return normalize_response_text(block.get("text"))
        if "content" in block:
            return normalize_response_text(block.get("content"))
        return ""
    if isinstance(content, Sequence) and not isinstance(content, (bytes, bytearray)):
        parts = [normalize_response_text(item) for item in content]
        return "\n".join(part for part in parts if part)
    block_type = getattr(content, "type", None)
    if block_type in {"text", "output_text"}:
        return normalize_response_text(getattr(content, "text", None))
    return ""
