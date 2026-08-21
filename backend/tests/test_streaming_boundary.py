import inspect
import json
from types import SimpleNamespace

import pytest

from agente.grafo.constructor import construir_grafo, langgraph_entrypoint
from api.servidor import (
    STREAM_TEXT_CHUNK_SIZE,
    USER_FACING_STREAM_NODES,
    _stream_phase_from_event,
    _stream_text_chunks,
    _stream_text_from_event,
    extract_public_text,
    sanitize_public_state,
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


def test_no_model_node_is_allowed_to_stream_public_text() -> None:
    blocks = [
        {"type": "text", "text": "Hola"},
        {"type": "output_text", "content": " mundo"},
    ]

    assert extract_public_text("texto directo") == "texto directo"
    assert extract_public_text({"type": "text", "text": "private object"}) == ""
    assert _stream_text_from_event(chat_model_event("devuelve_respuesta", blocks)) == ""


@pytest.mark.parametrize("node", ["obtiene_pregunta", "obtiene_schema", "construye_cypher"])
def test_internal_nodes_never_stream_model_chunks(node: str) -> None:
    assert _stream_text_from_event(chat_model_event(node, "private")) == ""


def test_stream_allowlist_has_no_model_nodes() -> None:
    graph_nodes = construir_grafo().get_graph().nodes

    assert USER_FACING_STREAM_NODES <= graph_nodes.keys()
    assert USER_FACING_STREAM_NODES == set()


def test_public_answer_is_emitted_as_ordered_cumulative_chunks() -> None:
    answer = "Encontré datos académicos y de empleabilidad."

    chunks = list(_stream_text_chunks(answer))

    assert len(chunks) > 1
    assert "".join(chunks) == answer
    assert all(0 < len(chunk) <= STREAM_TEXT_CHUNK_SIZE for chunk in chunks)


def test_stream_chunk_size_must_be_positive() -> None:
    with pytest.raises(ValueError, match="chunk_size must be positive"):
        list(_stream_text_chunks("respuesta", chunk_size=0))


def test_langgraph_entrypoint_is_a_no_argument_factory() -> None:
    assert not inspect.signature(langgraph_entrypoint).parameters
    assert langgraph_entrypoint().get_graph().nodes


def test_final_state_publishes_rows_but_hides_query_internals() -> None:
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
        "filas": [{"total": 2}],
        "error": None,
    }
    assert json.loads(json.dumps(public)) == public


def test_nested_query_keys_are_removed_from_public_rows() -> None:
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

    assert sanitize_public_state(state) == {
        "filas": [
            {
                "empresa": "Acme",
                "ofertas": 3,
                "detalle": {"sector": "Tecnologia"},
            }
        ],
    }


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
        "filas": [{"total": 2}],
    }


def test_stream_phase_only_exposes_known_user_facing_labels() -> None:
    event = {
        "event": "on_chain_start",
        "metadata": {"langgraph_node": "cypher_guard"},
    }

    assert _stream_phase_from_event(event) == "validando_consulta"
    assert _stream_phase_from_event({"event": "on_chain_start", "name": "private_node"}) == ""
