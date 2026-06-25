#!/usr/bin/env python3
"""
Agente CIAR de consola con LangGraph + LangSmith + LLM local por Ollama.

Uso:
  python3 agente_consola.py
  python3 agente_consola.py --model qwen3-coder:30b
"""
from __future__ import annotations

import argparse
import json
import os
import re
import textwrap
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from neo4j import GraphDatabase

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return False

try:
    from langsmith import traceable
except ImportError:
    def traceable(*_args, **_kwargs):
        def decorator(func):
            return func
        return decorator


BASE_DIR = Path(__file__).resolve().parent
ONTOLOGY_PATH = BASE_DIR / "ontologia.json"
MERMAID_PATH = BASE_DIR / "langgraph_agent.mmd"

READ_ONLY_START = ("match", "with", "return", "call db.", "call apoc.meta")
WRITE_WORDS = {
    "create", "merge", "delete", "detach", "set", "remove", "drop", "load",
    "periodic", "apoc.periodic", "dbms.", "constraint", "index"
}


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    schema_text: str


def load_env() -> None:
    load_dotenv(BASE_DIR / ".env")
    os.environ.setdefault("LANGSMITH_PROJECT", "ciar-local-langgraph")


@lru_cache(maxsize=1)
def ontology() -> dict:
    return json.loads(ONTOLOGY_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def neo4j_driver():
    uri = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    return driver


def csv_headers(csv_name: str) -> list[str]:
    path = BASE_DIR / csv_name
    with path.open(encoding="utf-8-sig") as file:
        first_line = file.readline().strip()
    return [header.strip() for header in first_line.split(",") if header.strip()]


@traceable(run_type="chain", name="build_ciar_schema_text")
def build_schema_text() -> str:
    data = ontology()
    lines = [
        "ONTOLOGIA CIAR EN NEO4J",
        "Usa exactamente estos labels, propiedades y relaciones.",
        "",
        "NODOS",
    ]

    for entity in data["entidades"]:
        source = entity["fuente"]
        headers = csv_headers(source["csv"])
        if source.get("nombre_col"):
            headers = [*headers, "nombre_norm"]
        lines.append(
            f"- :{entity['label']} pk={entity['pk']} props={', '.join(dict.fromkeys(headers))}"
        )

    lines.append("")
    lines.append("RELACIONES DIRIGIDAS")
    for relation in data["relaciones"]:
        lines.append(f"- (:{relation['source']})-[:{relation['tipo']}]->(:{relation['target']})")

    lines.append("")
    lines.append("REGLAS IMPORTANTES")
    lines.append("- Todos los IDs son hashes con prefijo y ya existen en las propiedades id_*.")
    lines.append("- Para buscar por nombre usa nombre_norm cuando exista: texto en minusculas y sin tildes.")
    lines.append("- No inventes labels, relaciones ni propiedades fuera de este schema.")
    lines.append("- Solo genera consultas de lectura: MATCH/WITH/RETURN/CALL db.*.")
    lines.append("- Usa LIMIT 25 salvo que el usuario pida conteo, promedio o ranking especifico.")
    lines.append("- Si necesitas contar, usa count(...). Si necesitas ranking, ordena con ORDER BY y LIMIT.")
    lines.append("- Silabo se escribe sin tilde como label: :Silabo.")
    lines.append("- EvalDesempeno es el label de evaluacion de desempeno.")
    return "\n".join(lines)


def llm() -> ChatOllama:
    return ChatOllama(
        model=os.getenv("OLLAMA_MODEL", "qwen3:14b"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        temperature=float(os.getenv("OLLAMA_TEMPERATURE", "0")),
        num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "32768")),
    )


def clean_cypher(text: str) -> str:
    cypher = (text or "").strip()
    if "```" in cypher:
        blocks = cypher.split("```")
        cypher = blocks[1] if len(blocks) > 1 else cypher
    cypher = re.sub(r"^\s*cypher\s*", "", cypher, flags=re.IGNORECASE).strip()
    return cypher.strip("`").strip()


def validate_read_only_cypher(cypher: str) -> None:
    lowered = re.sub(r"\s+", " ", cypher.lower()).strip()
    if not lowered.startswith(READ_ONLY_START):
        raise ValueError("La consulta generada no empieza como lectura segura.")
    words = set(re.findall(r"[a-zA-Z_.]+", lowered))
    blocked = sorted(words & WRITE_WORDS)
    if blocked:
        raise ValueError(f"La consulta contiene operaciones no permitidas: {', '.join(blocked)}")


@traceable(run_type="llm", name="generate_cypher_with_local_llm")
def generate_cypher(question: str, schema_text: str, previous_error: str | None = None) -> str:
    repair = ""
    if previous_error:
        repair = f"\nLa consulta anterior fallo con este error. Corrigela:\n{previous_error}\n"
    prompt = f"""
    Convierte la pregunta del usuario a Cypher para Neo4j.

    {schema_text}
    {repair}

    Devuelve UNICAMENTE Cypher, sin markdown ni explicaciones.

    Pregunta: {question}
    Cypher:
    """
    response = llm().invoke([
        SystemMessage(content="Eres un experto en Neo4j Cypher. Generas consultas seguras de solo lectura."),
        HumanMessage(content=textwrap.dedent(prompt).strip()),
    ])
    cypher = clean_cypher(str(response.content))
    validate_read_only_cypher(cypher)
    return cypher


@traceable(run_type="tool", name="run_neo4j_read_query")
def run_neo4j_read_query(cypher: str) -> list[dict]:
    validate_read_only_cypher(cypher)
    with neo4j_driver().session() as session:
        records = session.execute_read(lambda tx: tx.run(cypher))
        return [dict(record) for record in records]


@tool
@traceable(run_type="tool", name="buscar_grafo_ciar")
def buscar_grafo_ciar(pregunta: str) -> str:
    """Consulta el grafo Neo4j CIAR completo usando Cypher generado desde la pregunta."""
    schema_text = build_schema_text()
    last_error: str | None = None
    for attempt in range(2):
        try:
            cypher = generate_cypher(pregunta, schema_text, previous_error=last_error)
            rows = run_neo4j_read_query(cypher)
            return json.dumps({
                "cypher": cypher,
                "row_count": len(rows),
                "rows": rows[:50],
                "truncated": len(rows) > 50,
                "attempt": attempt + 1,
            }, ensure_ascii=False, default=str)
        except Exception as exc:
            last_error = str(exc)
    return json.dumps({
        "error": last_error,
        "hint": "No pude generar o ejecutar una consulta Cypher segura para esa pregunta."
    }, ensure_ascii=False)


@tool
@traceable(run_type="tool", name="describir_ontologia_ciar")
def describir_ontologia_ciar() -> str:
    """Resume labels, relaciones y conteos disponibles en la ontologia CIAR."""
    data = ontology()
    summary: dict[str, object] = {
        "labels": [entity["label"] for entity in data["entidades"]],
        "relationships": [
            f"{rel['source']}-[:{rel['tipo']}]->{rel['target']}" for rel in data["relaciones"]
        ],
    }
    try:
        with neo4j_driver().session() as session:
            summary["node_counts"] = {
                record["label"]: record["total"]
                for record in session.run("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS total")
            }
            summary["relationship_counts"] = {
                record["type"]: record["total"]
                for record in session.run("MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS total")
            }
    except Exception as exc:
        summary["neo4j_warning"] = str(exc)
    return json.dumps(summary, ensure_ascii=False, indent=2, default=str)


TOOLS = [buscar_grafo_ciar, describir_ontologia_ciar]
TOOL_NODE = ToolNode(TOOLS)


def assistant_node(state: AgentState) -> dict:
    model = llm().bind_tools(TOOLS)
    system_prompt = f"""
    Eres el agente de consola CIAR.

    Responde en espanol claro y breve. Para preguntas sobre datos, usa SIEMPRE
    la tool buscar_grafo_ciar. Para preguntas sobre estructura del grafo, usa
    describir_ontologia_ciar. No inventes cifras: si Neo4j devuelve vacio, dilo.

    Schema disponible:
    {state['schema_text']}
    """
    response = model.invoke([SystemMessage(content=textwrap.dedent(system_prompt).strip()), *state["messages"]])
    return {"messages": [response]}


def should_continue(state: AgentState) -> Literal["tools", "__end__"]:
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("assistant", assistant_node)
    builder.add_node("tools", TOOL_NODE)
    builder.add_edge(START, "assistant")
    builder.add_conditional_edges("assistant", should_continue, {"tools": "tools", END: END})
    builder.add_edge("tools", "assistant")
    return builder.compile(checkpointer=MemorySaver())


def save_mermaid(app) -> None:
    MERMAID_PATH.write_text(app.get_graph().draw_mermaid(), encoding="utf-8")


def print_langsmith_status() -> None:
    tracing = os.getenv("LANGSMITH_TRACING", "").lower() == "true"
    api_key = bool(os.getenv("LANGSMITH_API_KEY"))
    project = os.getenv("LANGSMITH_PROJECT", "ciar-local-langgraph")
    status = "activo" if tracing and api_key else "inactivo"
    print(f"LangSmith: {status} | proyecto={project}")


def run_console(model_name: str | None = None) -> None:
    if model_name:
        os.environ["OLLAMA_MODEL"] = model_name

    graph = build_graph()
    save_mermaid(graph)
    schema_text = build_schema_text()
    session_id = f"ciar-console-{uuid.uuid4().hex[:8]}"

    print("Agente CIAR consola")
    print(f"Ollama: {os.getenv('OLLAMA_MODEL', 'qwen3:14b')} | {os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')}")
    print_langsmith_status()
    print(f"LangGraph Mermaid: {MERMAID_PATH}")
    print("Comandos: /schema, /salir\n")

    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not question:
            continue
        if question.lower() in {"/salir", "salir", "exit", "quit"}:
            break
        if question.lower() == "/schema":
            print(schema_text[:6000])
            continue

        config = {
            "configurable": {"thread_id": session_id},
            "tags": ["ciar", "console", "langgraph", "ollama", os.getenv("OLLAMA_MODEL", "local")],
            "metadata": {
                "ontology": "graficosnodos-full",
                "app": "ciar-console-agent",
                "session_id": session_id,
            },
            "recursion_limit": int(os.getenv("LANGGRAPH_RECURSION_LIMIT", "8")),
        }
        inputs = {"messages": [HumanMessage(content=question)], "schema_text": schema_text}
        final_answer = ""

        try:
            for update in graph.stream(inputs, config=config, stream_mode="updates"):
                if "assistant" in update:
                    message = update["assistant"]["messages"][-1]
                    tool_calls = getattr(message, "tool_calls", None)
                    if tool_calls:
                        names = ", ".join(call["name"] for call in tool_calls)
                        print(f"  LangGraph -> tools: {names}")
                    elif message.content:
                        final_answer = str(message.content)
                if "tools" in update:
                    print("  Neo4j -> resultado recibido")
            print(f"\n{final_answer.strip()}\n")
        except Exception as exc:
            print(f"\nError del agente: {exc}\n")

    try:
        neo4j_driver().close()
    except Exception:
        pass
    print("Listo.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="Modelo local de Ollama, ej. qwen3-coder:30b o qwen3:14b")
    args = parser.parse_args()
    load_env()
    run_console(args.model)


if __name__ == "__main__":
    main()
