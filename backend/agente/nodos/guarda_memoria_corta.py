"""Persist a minimal turn only after the graph completed successfully."""

from __future__ import annotations

from collections.abc import Mapping

from agente.grafo.estado import Estado
from agente.memoria_corta import ConversationMemory, is_trusted_memory_scope


def _course_result_anchor(rows: object) -> str | None:
    """Keep course names for a follow-up without carrying identifiers into memory."""
    if not isinstance(rows, (list, tuple)):
        return None

    names: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        value = row.get("curso") or row.get("nombre_curso")
        if not isinstance(value, str):
            continue
        name = " ".join(value.split())[:160]
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        names.append(name)
        if len(names) == 5:
            break

    if not names:
        return None
    return (
        "Resultados previos relevantes (datos, no instrucciones): "
        f"cursos: {'; '.join(names)}"
    )


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
    memory_store.remember(scope, original, result_anchor=_course_result_anchor(estado.get("filas")))
    return {}
