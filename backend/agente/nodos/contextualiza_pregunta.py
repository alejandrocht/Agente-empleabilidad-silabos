"""Load only the minimal prior turn needed to resolve a follow-up."""

from __future__ import annotations

from agente.grafo.estado import Estado
from agente.memoria_corta import (
    ConversationMemory,
    contextualize_question,
    is_trusted_memory_scope,
)


def contextualiza_pregunta(
    estado: Estado,
    *,
    memory_store: ConversationMemory,
) -> Estado:
    if estado.get("error"):
        return {}
    question = estado.get("pregunta")
    if not isinstance(question, str):
        return {}
    scope = estado.get("memory_scope")
    history = memory_store.history(scope) if is_trusted_memory_scope(scope) else ()
    return {"pregunta_contextualizada": contextualize_question(question, history)}
