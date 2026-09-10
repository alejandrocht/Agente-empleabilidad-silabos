import inspect
import json
from types import SimpleNamespace

import pytest

from agente.grafo.constructor import construir_grafo, langgraph_entrypoint
from api.servidor import (
    USER_FACING_STREAM_NODES,
    _stream_phase_from_event,
    _stream_text_from_event,
    extract_public_text,
    sanitize_public_state,
    stream_message_event,
    stream_progress_event,
)


def chat_model_event(node: str, content: object) -> dict[str, object]:
    return {
        "event": "on_chat_model_stream",
        "metadata": {"langgraph_node": node},
        "data": {"chunk": SimpleNamespace(content=content)},
    }


def test_internal_model_blocks_are_not_exposed_as_answer() -> None:
    blocks = [
        {"id": "internal-id", "type": "reasoning", "content": "private content"},
    ]

    assert _stream_text_from_event(chat_model_event("construye_cypher", blocks)) == ""


def test_only_answer_nodes_can_stream_public_text() -> None:
    blocks = [
        {"type": "text", "text": "Hola"},
        {"type": "output_text", "content": " mundo"},
    ]

    assert extract_public_text("texto directo") == "texto directo"
    assert extract_public_text({"type": "text", "text": "private object"}) == ""
    assert _stream_text_from_event(chat_model_event("redacta_respuesta", blocks)) == "Hola mundo"


@pytest.mark.parametrize("node", ["obtiene_pregunta", "obtiene_schema", "construye_cypher"])
def test_internal_nodes_never_stream_model_chunks(node: str) -> None:
    assert _stream_text_from_event(chat_model_event(node, "private")) == ""


def test_stream_allowlist_contains_only_answer_nodes() -> None:
    graph_nodes = construir_grafo().get_graph().nodes

    assert USER_FACING_STREAM_NODES <= graph_nodes.keys()
    assert USER_FACING_STREAM_NODES == {"redacta_respuesta", "responder_directo"}


def test_public_answer_uses_native_langgraph_message_events() -> None:
    event = stream_message_event("message-1", "redacta_respuesta", "Hola")
    payload = json.loads(event.split("data: ", 1)[1])

    assert event.startswith("event: messages\n")
    assert payload == [
        {"type": "ai", "id": "message-1", "content": "Hola"},
        {"langgraph_node": "redacta_respuesta"},
    ]


def test_progress_uses_native_langgraph_custom_events() -> None:
    event = stream_progress_event("Analizando la intención…", "analizando")
    payload = json.loads(event.split("data: ", 1)[1])

    assert event.startswith("event: custom\n")
    assert payload == {
        "type": "progress",
        "fase": "analizando",
        "texto": "Analizando la intención…",
    }


def test_langgraph_entrypoint_is_a_no_argument_factory() -> None:
    assert not inspect.signature(langgraph_entrypoint).parameters
    assert langgraph_entrypoint().get_graph().nodes


def test_final_state_publishes_response_and_query_but_hides_rows() -> None:
    state = {
        "respuesta": "Encontré 1 resultado para tu consulta.",
        "cypher": "MATCH (n:Carrera) RETURN n.nombre AS nombre LIMIT $limit",
        "parameters": {"limit": 10},
        "schema": {"labels": ["private"]},
        "filas": [{"total": 2}],
        "error": None,
    }

    public = sanitize_public_state(state)

    assert public == {
        "respuesta": "Encontré 1 resultado para tu consulta.",
        "cypher": "MATCH (n:Carrera) RETURN n.nombre AS nombre LIMIT $limit",
        "error": None,
    }
    assert json.loads(json.dumps(public)) == public


def test_rows_are_not_projected_to_public_state() -> None:
    state = {
        "filas": [
            {
                "empresa": "Acme",
                "ofertas": 3,
                "detalle": {
                    "sector": "Tecnologia",
                    "pregunta": "private question",
                    "variables": {"private": True},
                },
            }
        ],
    }

    assert sanitize_public_state(state) == {}


def test_public_rows_are_not_exposed_even_when_nested() -> None:
    state = {
        "filas": [
            {
                "curso_id": "CUR_INTERNO",
                "curso": "Analítica de Negocios",
                "detalle": {"id": "DETALLE_INTERNO", "area": "Datos"},
            }
        ],
    }

    assert sanitize_public_state(state) == {}


def test_query_internals_are_never_projected_publicly() -> None:
    state = {
        "respuesta": "Respuesta fundamentada",
        "cypher": "MATCH (n) RETURN n LIMIT 10",
        "parametros": {"limit": 10},
        "parameters": {"limit": 10},
        "schema": {"labels": ["private"]},
        "generated_query": {"cypher": "private"},
        "filas": [{"cypher": "private", "total": 2}],
    }

    assert sanitize_public_state(state) == {
        "respuesta": "Respuesta fundamentada",
    }


def test_stream_phase_only_exposes_known_user_facing_labels() -> None:
    event = {
        "event": "on_chain_start",
        "metadata": {"langgraph_node": "cypher_guard"},
    }

    assert _stream_phase_from_event(event) == "validando_consulta"
    assert _stream_phase_from_event({"event": "on_chain_start", "name": "private_node"}) == ""
