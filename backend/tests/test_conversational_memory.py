from __future__ import annotations

from agente.memoria_corta import ConversationMemory, derive_memory_scope
from agente.nodos.guarda_memoria_corta import guarda_memoria_corta


def test_memory_stores_only_the_original_question() -> None:
    memory = ConversationMemory(ttl_seconds=60, max_turns=2)
    scope = derive_memory_scope("server-secret", "user-a", "thread-a")

    memory.remember(scope, "¿Qué cursos enseñan SAP?")

    turns = memory.history(scope)
    assert len(turns) == 1
    assert turns[0].original_question == "¿Qué cursos enseñan SAP?"
    assert set(vars(turns[0])) == {"original_question", "created_at"}


def test_failed_turn_is_not_saved() -> None:
    memory = ConversationMemory(ttl_seconds=60)
    scope = derive_memory_scope("server-secret", "user-a", "thread-a")

    result = guarda_memoria_corta(
        {
            "pregunta": "Listá puestos privados",
            "memory_scope": scope,
            "respuesta": "No pude consultar.",
            "error": "query_failed",
        },
        memory_store=memory,
    )

    assert result == {}
    assert memory.history(scope) == ()


def test_successful_turn_saves_original_question_without_result_context() -> None:
    memory = ConversationMemory(ttl_seconds=60)
    scope = derive_memory_scope("server-secret", "user-a", "thread-a")

    result = guarda_memoria_corta(
        {
            "pregunta": "¿Qué cursos enseñan SAP?",
            "memory_scope": scope,
            "respuesta": "Encontré resultados.",
            "filas": [{"curso": "ERP"}],
            "error": None,
        },
        memory_store=memory,
    )

    assert result == {}
    assert [turn.original_question for turn in memory.history(scope)] == [
        "¿Qué cursos enseñan SAP?"
    ]


def test_improved_question_does_not_replace_original_memory_question() -> None:
    memory = ConversationMemory(ttl_seconds=60)
    scope = derive_memory_scope("server-secret", "user-a", "thread-a")

    guarda_memoria_corta(
        {
            "pregunta": "q puede hacer el curs de analis",
            "pregunta_original": "q puede hacer el curs de analis",
            "pregunta_mejorada": "¿Qué capacidades desarrolla el curso de Análisis?",
            "ruta": "cypher",
            "memory_scope": scope,
            "respuesta": "Encontré resultados.",
            "error": None,
        },
        memory_store=memory,
    )

    assert [turn.original_question for turn in memory.history(scope)] == [
        "q puede hacer el curs de analis"
    ]


def test_memory_ttl_and_turn_limit_are_enforced() -> None:
    now = [0.0]
    memory = ConversationMemory(ttl_seconds=10, max_turns=2, clock=lambda: now[0])
    scope = derive_memory_scope("server-secret", "user-a", "thread-a")

    for index in range(3):
        memory.remember(scope, f"pregunta-{index}")
        now[0] += 1

    assert [turn.original_question for turn in memory.history(scope)] == [
        "pregunta-1",
        "pregunta-2",
    ]
    now[0] = 12
    assert memory.history(scope) == ()


def test_memory_scopes_are_opaque_and_isolated() -> None:
    first = derive_memory_scope("server-secret", "user-a", "thread-a")
    second = derive_memory_scope("server-secret", "user-b", "thread-a")
    assert first != second
    assert len(first) == 64
    assert "user-a" not in first


def test_untrusted_scope_does_not_store_turn() -> None:
    memory = ConversationMemory(ttl_seconds=60)
    result = guarda_memoria_corta(
        {
            "pregunta": "consulta",
            "memory_scope": "scope-from-client",
            "respuesta": "respuesta",
            "error": None,
        },
        memory_store=memory,
    )
    assert result == {}
    assert memory.stats() == {"scopes": 0, "entries": 0}
