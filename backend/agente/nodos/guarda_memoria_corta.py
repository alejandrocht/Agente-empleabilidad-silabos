"""Persist a minimal turn only after the graph completed successfully."""

from __future__ import annotations

from agente.grafo.estado import Estado
from agente.memoria_corta import ConversationMemory, is_trusted_memory_scope


def guarda_memoria_corta(
    estado: Estado,
    *,
    memory_store: ConversationMemory,
) -> Estado:
    if estado.get("error") is not None:
        return {}
    scope = estado.get("memory_scope")
    original = estado.get("pregunta")
    contextualized = estado.get("pregunta_contextualizada")
    answer = estado.get("respuesta")
    if not is_trusted_memory_scope(scope):
        return {}
    if not isinstance(original, str) or not original:
        return {}
    if not isinstance(contextualized, str) or not contextualized:
        return {}
    if not isinstance(answer, str) or not answer:
        return {}
    memory_store.remember(scope, original)
    return {}
