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
import unicodedata
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

    # LangSmith solo traza si hay API key. Si la hay y no se dijo lo contrario,
    # activa el tracing y replica los alias LANGCHAIN_* por compatibilidad.
    has_key = bool(os.getenv("LANGSMITH_API_KEY"))
    tracing = os.getenv("LANGSMITH_TRACING", "").lower()
    if has_key and tracing not in {"true", "false"}:
        tracing = "true"
    tracing = "true" if (tracing == "true" and has_key) else "false"
    os.environ["LANGSMITH_TRACING"] = tracing
    os.environ["LANGCHAIN_TRACING_V2"] = tracing
    if tracing == "true":
        os.environ.setdefault("LANGCHAIN_ENDPOINT", os.getenv("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com"))
        os.environ.setdefault("LANGCHAIN_API_KEY", os.getenv("LANGSMITH_API_KEY", ""))
        os.environ.setdefault("LANGCHAIN_PROJECT", os.getenv("LANGSMITH_PROJECT", "ciar-local-langgraph"))


@lru_cache(maxsize=1)
def neo4j_driver():
    uri = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")
    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    return driver


@lru_cache(maxsize=1)
@traceable(run_type="chain", name="introspect_ciar_schema")
def introspect_schema() -> dict:
    """Descubre la ontologia en vivo desde Neo4j. Cacheado por sesion."""
    with neo4j_driver().session() as session:
        labels_counts: dict[str, int] = {
            r["label"]: r["total"]
            for r in session.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS total ORDER BY total DESC"
            )
            if r["label"]
        }
        labels = list(labels_counts.keys())

        if not labels:
            raise RuntimeError(
                "Neo4j esta vacio: no hay labels. Corre `python3 cargar_ontologia.py --reset` antes de iniciar el agente."
            )

        props_by_label: dict[str, list[str]] = {}
        for r in session.run(
            "CALL db.schema.nodeTypeProperties() YIELD nodeLabels, propertyName "
            "RETURN nodeLabels[0] AS label, collect(DISTINCT propertyName) AS props"
        ):
            if r["label"]:
                props_by_label[r["label"]] = sorted(r["props"])

        topology: list[dict] = []
        for r in session.run(
            "CALL db.schema.visualization() YIELD relationships "
            "UNWIND relationships AS rel "
            "RETURN labels(startNode(rel))[0] AS src, type(rel) AS rel_type, "
            "       labels(endNode(rel))[0] AS tgt"
        ):
            topology.append({"src": r["src"], "rel": r["rel_type"], "tgt": r["tgt"]})

        rel_freq: dict[str, int] = {
            r["rel"]: r["freq"]
            for r in session.run(
                "MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS freq"
            )
        }
        for t in topology:
            t["freq"] = rel_freq.get(t["rel"], 0)
        topology.sort(key=lambda x: x["freq"], reverse=True)

        # cada label puede usar "nombre", "nombre_carrera", "nombre_curso", etc.
        # detectamos la primera prop tipo nombre* (excepto nombre_norm).
        name_props: dict[str, str] = {}
        for label, props in props_by_label.items():
            for p in props:
                if p == "nombre":
                    name_props[label] = p
                    break
                if p.startswith("nombre_") and p != "nombre_norm":
                    name_props.setdefault(label, p)

        samples: dict[str, list[str]] = {}
        for label, name_prop in name_props.items():
            rows = session.run(
                f"MATCH (n:`{label}`) WHERE n.`{name_prop}` IS NOT NULL "
                f"RETURN n.`{name_prop}` AS sample LIMIT 5"
            )
            values = [r["sample"] for r in rows if r["sample"]]
            if values:
                samples[label] = values

    return {
        "labels": labels_counts,
        "props": props_by_label,
        "topology": topology,
        "samples": samples,
    }


@traceable(run_type="chain", name="build_ciar_schema_text")
def build_schema_text() -> str:
    intro = introspect_schema()
    lines = [
        "ONTOLOGIA CIAR EN NEO4J (descubierta en vivo)",
        "Usa exactamente estos labels, relaciones y propiedades.",
        "",
        "NODOS (label, conteo, propiedades)",
    ]
    for label, total in intro["labels"].items():
        props = intro["props"].get(label, [])
        props_str = ", ".join(props) if props else "(sin propiedades indexadas)"
        lines.append(f"- :{label} ({total} nodos) props: {props_str}")

    lines.append("")
    lines.append("RELACIONES (sin dirección para evitar errores, ordenadas por densidad)")
    for t in intro["topology"]:
        lines.append(f"- (:{t['src']})-[:{t['rel']}]-(:{t['tgt']})  [freq: {t.get('freq', 0)}]")

    if intro["samples"]:
        lines.append("")
        lines.append("EJEMPLOS DE DATOS REALES (usa estos nombres antes de inventar)")
        for label, names in intro["samples"].items():
            lines.append(f"- {label}: {', '.join(names)}")

    lines.append("")
    lines.append("REGLAS DE CONSULTA")
    lines.append("- Para buscar texto usa SIEMPRE CONTAINS con nombre_norm (ej: c.nombre_norm CONTAINS 'sistemas'). Texto en minusculas y sin tildes.")
    lines.append("- Si el usuario pregunta por una entidad especifica (Carrera, Puesto, Empresa), PRIMERO valida el nombre real con una consulta exploratoria (CONTAINS) antes de la consulta final.")
    lines.append("- No inventes labels, relaciones ni propiedades fuera de los listados arriba.")
    lines.append("- IMPORTANTE: Para evitar errores por direccion invertida, usa SIEMPRE relaciones sin direccion (sin flecha) en tus MATCH. Ejemplo: MATCH (a)-[:REL]-(b). NUNCA uses -> ni <-.")
    lines.append("- Solo lectura: MATCH/WITH/RETURN/CALL db.*.")
    lines.append("- Usa LIMIT 25 salvo que el usuario pida conteo, promedio o ranking.")
    lines.append("- Para count/ranking usa count(...) y ORDER BY.")
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


def validate_cypher_schema(cypher: str) -> None:
    """Verifica que los labels y rel types usados existen en el schema live de Neo4j."""
    intro = introspect_schema()
    known_labels = set(intro["labels"].keys())
    known_rels = {t["rel"] for t in intro["topology"]}

    # rel types: dentro de [ ... ]
    used_rels: set[str] = set()
    for rel_block in re.findall(r"\[[^\]]*\]", cypher):
        m = re.search(r":\s*([\w|`Ññ]+)", rel_block)
        if m:
            for token in m.group(1).split("|"):
                token = token.strip("`").strip()
                if token and token not in {"r", "rel"}:
                    used_rels.add(token)

    # labels: dentro de ( ... ), tras ":" pueden venir multi-label separados por ":"
    used_labels: set[str] = set()
    for lab_block in re.findall(r"\(\s*\w*\s*:\s*([\w:`Ññ]+)", cypher):
        for token in lab_block.split(":"):
            token = token.strip("`").strip()
            if token:
                used_labels.add(token)

    unknown_labels = sorted(used_labels - known_labels)
    unknown_rels = sorted(used_rels - known_rels)
    problems = []
    if unknown_labels:
        problems.append(
            f"labels inventados {unknown_labels}; usa solo {sorted(known_labels)}"
        )
    if unknown_rels:
        problems.append(
            f"relaciones inventadas {unknown_rels}; usa solo {sorted(known_rels)}"
        )

    # nombre_norm con igualdad → siempre incorrecto en Cypher final.
    # La búsqueda por texto va en resolver_entidad; el Cypher usa id_*.
    if re.search(r"nombre_norm\s*[=:]\s*['\"]", cypher, re.IGNORECASE):
        problems.append(
            "nombre_norm con igualdad (= o :) no permitido en Cypher final. "
            "Llama a resolver_entidad para obtener el id_* y usalo en su lugar."
        )
    # CONTAINS en Cypher final → señal de que saltó el paso resolver_entidad.
    if re.search(r"\bCONTAINS\b", cypher, re.IGNORECASE):
        problems.append(
            "CONTAINS no permitido en Cypher final. "
            "Llama a resolver_entidad primero para obtener id_* y filtra por id."
        )

    if "->" in cypher or "<-" in cypher:
        problems.append(
            "Uso de flechas (-> o <-) detectado. Para evitar errores de dirección, DEBES escribir TODAS las relaciones SIN FLECHAS de dirección. Ejemplo incorrecto: ()-[:REL]->(). Ejemplo correcto: ()-[:REL]-()."
        )

    if problems:
        raise ValueError("Schema invalido: " + " | ".join(problems))


FEW_SHOT_EXAMPLES = """
REGLA DE ORO: Si la pregunta menciona una entidad por nombre (carrera, curso, empresa,
puesto, competencia, habilidad, herramienta, industria), el agente PRIMERO llama a
resolver_entidad para obtener el id_* real, y LUEGO arma el Cypher usando ese id.
NUNCA uses nombre_norm en el Cypher final. NUNCA uses CONTAINS en el Cypher final.

EJEMPLOS (patron 2 pasos: resolver → id en Cypher)

# Paso 1: resolver_entidad("sistemas", "Carrera")
# → devuelve {id_carrera: "CAR_01375f53651cff38", nombre: "INGENIERÍA DE SISTEMAS"}
# Paso 2: Cypher con ese id (SIN FLECHAS DE DIRECCION EN LAS RELACIONES):
Pregunta: cuantos cursos tiene la carrera de sistemas
Cypher: MATCH (c:Carrera {id_carrera: 'CAR_01375f53651cff38'})-[:CONTIENE]-(cu:Curso) RETURN count(DISTINCT cu) AS total

# Paso 1: resolver_entidad("bcp", "Empresa")
# → devuelve {id_empresa: "EMP_abc123", nombre: "BANCO DE CREDITO BCP"}
# Paso 2:
Pregunta: cuantas ofertas publico BCP
Cypher: MATCH (e:Empresa {id_empresa: 'EMP_abc123'})-[:PUBLICA]-(o:OfertaLaboral) RETURN count(o) AS ofertas

# Paso 1: resolver_entidad("python", "Herramienta")
# → devuelve {id_herramienta: "HER_xyz789", nombre: "Python"}
# Paso 2:
Pregunta: que carreras cubren Python en su curricula
Cypher: MATCH (h:Herramienta {id_herramienta: 'HER_xyz789'})-[:ENSEÑA_HERRAMIENTA]-(:CoberturaCurricular)-[:TIENE_COBERTURA]-(:Curso)-[:CONTIENE]-(c:Carrera) RETURN DISTINCT c.nombre_carrera LIMIT 25

# Paso 1: resolver_entidad("sistemas", "Carrera")
# → id_carrera: "CAR_01375f53651cff38"
# Paso 2: brecha herramientas (lo que pide mercado y carrera no ensena)
Pregunta: que herramientas faltan en Ingenieria de Sistemas vs lo que pide el mercado
Cypher: MATCH (carr:Carrera {id_carrera: 'CAR_01375f53651cff38'})-[:CONTIENE]-(:Curso)-[:TIENE_COBERTURA]-(:CoberturaCurricular)-[:ENSEÑA_HERRAMIENTA]-(h:Herramienta) WITH carr, collect(DISTINCT h.id_herramienta) AS ensenadas MATCH (carr)-[:DIRIGE_A]-(:OfertaLaboral)-[:TIENE_REQUERIMIENTO]-(:RequerimientoLaboral)-[:REQUIERE_HERRAMIENTA]-(hm:Herramienta) WHERE NOT hm.id_herramienta IN ensenadas RETURN hm.nombre_herramienta AS brecha, count(*) AS demanda ORDER BY demanda DESC LIMIT 15

# Sin entidad especifica → Cypher directo (no necesita resolver_entidad)
Pregunta: cuantas carreras hay
Cypher: MATCH (c:Carrera) RETURN count(c) AS total

Pregunta: top 5 empresas con mas ofertas laborales
Cypher: MATCH (e:Empresa)-[:PUBLICA]-(o:OfertaLaboral) RETURN e.nombre AS empresa, count(o) AS ofertas ORDER BY ofertas DESC LIMIT 5

Pregunta: que competencias pide mas el mercado
Cypher: MATCH (:RequerimientoLaboral)-[:REQUIERE_COMPETENCIA]-(c:Competencia) RETURN c.nombre_competencia AS competencia, count(*) AS demanda ORDER BY demanda DESC LIMIT 10

Pregunta: promedio de puntaje de evaluacion de desempeno por carrera
Cypher: MATCH (e:EvalDesempeno)-[:EVALUA_CARRERA]-(c:Carrera) RETURN c.nombre_carrera AS carrera, avg(e.puntaje_general) AS promedio ORDER BY promedio DESC LIMIT 25
""".strip()


@traceable(run_type="llm", name="generate_cypher_with_local_llm")
def generate_cypher(question: str, schema_text: str, previous_error: str | None = None) -> str:
    repair = ""
    if previous_error:
        repair = f"\nLa consulta anterior fallo con este error. Corrigela siguiendo el schema y los ejemplos:\n{previous_error}\n"
    prompt = f"""
    Convierte la pregunta del usuario a Cypher para Neo4j.

    {schema_text}

    {FEW_SHOT_EXAMPLES}
    {repair}

    Devuelve UNICAMENTE Cypher, sin markdown ni explicaciones.

    Pregunta: {question}
    Cypher:
    """
    response = llm().invoke([
        SystemMessage(content="Eres un experto en Neo4j Cypher. Generas consultas seguras de solo lectura que respetan el schema descubierto en vivo."),
        HumanMessage(content=textwrap.dedent(prompt).strip()),
    ])
    cypher = clean_cypher(str(response.content))
    validate_read_only_cypher(cypher)
    validate_cypher_schema(cypher)
    return cypher


@traceable(run_type="tool", name="run_neo4j_read_query")
def run_neo4j_read_query(cypher: str) -> list[dict]:
    validate_read_only_cypher(cypher)
    with neo4j_driver().session() as session:
        return session.execute_read(lambda tx: [dict(record) for record in tx.run(cypher)])


_RESOLVER_NEEDED = "resolver_entidad"

@tool
@traceable(run_type="tool", name="buscar_grafo_ciar")
def buscar_grafo_ciar(pregunta: str) -> str:
    """Consulta el grafo Neo4j CIAR completo usando Cypher generado desde la pregunta.

    IMPORTANTE: Si la pregunta menciona una entidad por nombre (carrera, empresa,
    curso, puesto, competencia, habilidad, herramienta, industria), debes llamar
    primero a `resolver_entidad` para obtener el id_* real. 
    LUEGO, al llamar a esta herramienta, DEBES incluir ese ID dentro del texto de la pregunta.
    Ejemplo: "en que industrias trabajan los de sistemas (ID: CAR_01375f...)"
    Esta tool no acepta CONTAINS ni nombre_norm.
    """
    schema_text = build_schema_text()
    last_error: str | None = None
    for attempt in range(2):
        try:
            cypher = generate_cypher(pregunta, schema_text, previous_error=last_error)
            rows = run_neo4j_read_query(cypher)
            return json.dumps({
                "cypher": cypher,
                "row_count": len(rows),
                "rows": rows,
                "attempt": attempt + 1,
            }, ensure_ascii=False, default=str)
        except ValueError as exc:
            error_msg = str(exc)
            # si el validador rechaza por CONTAINS o nombre_norm, romper el loop
            # de inmediato e indicar al assistant que debe usar resolver_entidad primero
            if _RESOLVER_NEEDED in error_msg or "CONTAINS" in error_msg or "nombre_norm" in error_msg:
                return json.dumps({
                    "accion_requerida": "resolver_entidad",
                    "instruccion": (
                        "Antes de llamar a buscar_grafo_ciar, llama a resolver_entidad "
                        "con el nombre de la entidad mencionada para obtener su id_*. "
                        "Luego incluye ese id en la pregunta o indica el id al llamar "
                        "a buscar_grafo_ciar."
                    ),
                    "error_validacion": error_msg,
                }, ensure_ascii=False)
            last_error = error_msg
        except Exception as exc:
            last_error = str(exc)
    return json.dumps({
        "error": last_error,
        "hint": "No pude generar o ejecutar una consulta Cypher segura para esa pregunta."
    }, ensure_ascii=False)


@tool
@traceable(run_type="tool", name="describir_ontologia_ciar")
def describir_ontologia_ciar() -> str:
    """Resume labels, relaciones y conteos del grafo CIAR descubiertos en vivo desde Neo4j."""
    try:
        intro = introspect_schema()
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    summary = {
        "labels_with_counts": intro["labels"],
        "properties_by_label": intro["props"],
        "relationships": [
            {"source": t["src"], "type": t["rel"], "target": t["tgt"], "freq": t.get("freq", 0)}
            for t in intro["topology"]
        ],
        "sample_names": intro["samples"],
    }
    return json.dumps(summary, ensure_ascii=False, indent=2, default=str)


@tool
@traceable(run_type="tool", name="resolver_entidad")
def resolver_entidad(texto: str, label: str = "") -> str:
    """Valida si un texto del usuario corresponde a una entidad real en el grafo CIAR.

    USA ESTA TOOL ANTES de armar el Cypher final cuando el usuario menciona una entidad
    especifica por nombre (carrera, curso, empresa, puesto, competencia, habilidad,
    herramienta, industria). Te devuelve el nombre exacto y el id real en la base.

    Args:
        texto: termino o palabra clave a buscar (ej. "sistemas", "BCP", "python").
        label: opcional, restringe la busqueda a un label especifico
               (ej. "Carrera", "Empresa", "Curso"). Si se omite, busca en todos los
               labels que tengan nombre_norm.
    """
    intro = introspect_schema()
    norm = unicodedata.normalize("NFKD", (texto or "").lower())
    norm = "".join(c for c in norm if not unicodedata.combining(c)).strip()
    if not norm:
        return json.dumps({"error": "texto vacio"}, ensure_ascii=False)

    if label:
        candidates = [label] if label in intro["labels"] else []
        if not candidates:
            return json.dumps(
                {"error": f"label '{label}' no existe", "labels_validos": sorted(intro["labels"].keys())},
                ensure_ascii=False,
            )
    else:
        candidates = [l for l, props in intro["props"].items() if "nombre_norm" in props]

    matches: dict[str, list[dict]] = {}
    with neo4j_driver().session() as session:
        for lbl in candidates:
            name_prop = None
            id_prop = None
            for p in intro["props"].get(lbl, []):
                if p == "nombre" and not name_prop:
                    name_prop = p
                elif p.startswith("nombre_") and p != "nombre_norm" and not name_prop:
                    name_prop = p
                if p.startswith("id_") and not id_prop:
                    id_prop = p
            if not name_prop:
                continue
            tokens = norm.split()
            where_clauses = [f"n.nombre_norm CONTAINS $q{i}" for i in range(len(tokens))]
            where_str = " AND ".join(where_clauses)

            cypher = (
                f"MATCH (n:`{lbl}`) WHERE {where_str} "
                f"RETURN n.`{name_prop}` AS nombre"
                + (f", n.`{id_prop}` AS id" if id_prop else "")
                + " LIMIT 5"
            )
            params = {f"q{i}": t for i, t in enumerate(tokens)}
            rows = session.execute_read(lambda tx, c=cypher, p=params: [dict(r) for r in tx.run(c, **p)])
            if rows:
                matches[lbl] = rows

    if not matches:
        return json.dumps(
            {"resultado": f"sin coincidencias para '{texto}' (normalizado '{norm}')",
             "sugerencia": "usa menos texto, sin restringir el label, o revisa la ortografia"},
            ensure_ascii=False,
        )
    return json.dumps(
        {"texto_normalizado": norm, "matches": matches},
        ensure_ascii=False,
        indent=2,
        default=str,
    )


TOOLS = [buscar_grafo_ciar, describir_ontologia_ciar, resolver_entidad]
TOOL_NODE = ToolNode(TOOLS)


def assistant_node(state: AgentState) -> dict:
    # primer turno: aun no hay ningun ToolMessage en el estado -> forzamos uso de tool.
    # esto evita que el modelo chico responda directo sin consultar el grafo.
    has_tool_result = any(getattr(m, "type", None) == "tool" for m in state["messages"])
    base = llm()
    model = base.bind_tools(TOOLS)

    system_prompt = f"""
    Eres el agente de consola CIAR.

    RESPONDE EXCLUSIVAMENTE EN ESPAÑOL. ESTÁ TOTALMENTE PROHIBIDO USAR CHINO, INGLÉS U OTRO IDIOMA.

    PROTOCOLO OBLIGATORIO DE 2 PASOS:
    1. Si el usuario menciona cualquier entidad por nombre (carrera, curso, empresa,
       puesto, competencia, habilidad, herramienta, industria), llama PRIMERO a
       `resolver_entidad` para obtener el id_* real de esa entidad.
       - Si `resolver_entidad` devuelve "sin coincidencias", deduce si el usuario usó una abreviatura o siglas (ej: "rrhh" -> "recursos humanos", "arqui" -> "arquitectura") y vuelve a llamar a la herramienta con el nombre completo.
    2. Luego llama a `buscar_grafo_ciar` ASEGURÁNDOTE DE INCLUIR EL ID que obtuviste dentro del texto de la pregunta. 
       Por ejemplo, si el usuario preguntó "cursos de sistemas" y obtuviste el ID "CAR_123", debes llamar a la herramienta enviando: `{{"pregunta": "cursos de sistemas (ID: CAR_123)"}}`.
       NUNCA uses nombre_norm, CONTAINS ni comparaciones de texto en el Cypher final.

    OTRAS REGLAS:
    - Para preguntas sin entidad especifica (conteos globales, rankings generales),
      puedes llamar directamente a `buscar_grafo_ciar`.
    - Para preguntas sobre estructura/ontologia del grafo, usa `describir_ontologia_ciar`.
    - NUNCA inventes cifras ni nombres. Si Neo4j devuelve vacio, dilo.

    Schema disponible:
    {state['schema_text']}
    """
    
    messages_to_invoke = [SystemMessage(content=textwrap.dedent(system_prompt).strip())] + list(state["messages"])
    
    # 1. Fuerza al LLM chico a prestar atencion al error del tool
    last_msg = state["messages"][-1]
    if getattr(last_msg, "type", None) == "tool" and "resolver_entidad" in str(getattr(last_msg, "content", "")):
        messages_to_invoke.append(SystemMessage(
            content="REGLA CRITICA: La herramienta anterior fallo porque debes usar `resolver_entidad`. LLAMA A `resolver_entidad` AHORA. No llames a buscar_grafo_ciar."
        ))

    # 2. Mecanismo anti-bucle si se acerca al limite (ej. 15 mensajes)
    if len(state["messages"]) > 15:
        # Quitamos las tools para obligarlo a dar una respuesta en texto y terminar
        try:
            model = base
        except Exception:
            pass
        messages_to_invoke.append(SystemMessage(
            content="Has intentado buscar muchas veces sin exito. Responde al usuario que hubo un problema tecnico procesando su solicitud y termina."
        ))

    response = model.invoke(messages_to_invoke)

    # Parche de rescate: Si Ollama devuelve el Tool Call como texto JSON crudo en vez del formato nativo
    if not getattr(response, "tool_calls", []) and response.content:
        text = str(response.content).strip()
        
        # Buscar un bloque de codigo JSON en cualquier parte del texto
        import re
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
        else:
            # Si no hay bloque markdown, intentar encontrar llave de apertura y cierre
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                text = text[start:end+1].strip()

        if text.startswith("{") and text.endswith("}") and '"name"' in text and '"arguments"' in text:
            try:
                import json
                import uuid
                from langchain_core.messages import AIMessage
                
                data = json.loads(text)
                if "name" in data and "arguments" in data:
                    args = data["arguments"] if isinstance(data["arguments"], dict) else json.loads(data["arguments"])
                    new_tool_call = {
                        "name": data["name"],
                        "args": args,
                        "id": f"call_{uuid.uuid4().hex[:8]}"
                    }
                    response = AIMessage(
                        content="", 
                        tool_calls=[new_tool_call],
                        id=getattr(response, "id", None) or str(uuid.uuid4()),
                        response_metadata=getattr(response, "response_metadata", {})
                    )
            except Exception:
                pass

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
            print(f"  [LangSmith] Rastreando ejecución en el proyecto: {os.getenv('LANGSMITH_PROJECT', 'ciar-local-langgraph')}")
            print("  [Flujo LangGraph] Iniciando recorrido por los nodos del agente...")

            for update in graph.stream(inputs, config=config, stream_mode="updates"):
                for node_name in update.keys():
                    print(f"  [Flujo LangGraph] El agente ejecutó y salió del nodo: '{node_name}'")

                if "assistant" in update:
                    message = update["assistant"]["messages"][-1]
                    tool_calls = getattr(message, "tool_calls", None)
                    if tool_calls:
                        names = ", ".join(call["name"] for call in tool_calls)
                        print(f"  [Camino] El agente decidió usar la herramienta: {names}")
                    elif message.content:
                        final_answer = str(message.content)
                if "tools" in update:
                    messages = update["tools"]["messages"]
                    for msg in messages:
                        if msg.name == "buscar_grafo_ciar":
                            try:
                                data = json.loads(msg.content)
                                if "cypher" in data:
                                    path_match = re.findall(r'[:]([A-Za-z_]+)(?=[\]\)\s{])', data['cypher'].split('RETURN')[0].split('WHERE')[0])
                                    if path_match:
                                        print(f"  [Razonamiento] Recorrido de la IA: \033[93m{' -> '.join(path_match)}\033[0m")
                                    print(f"  [Razonamiento] Código exacto en Neo4j:\n    \033[96m{data['cypher']}\033[0m")
                                    print(f"  [Razonamiento] Neo4j devolvió {data.get('row_count', 0)} resultados.")
                                    if data.get("rows"):
                                        muestra = str(data["rows"][0])[:150]
                                        print(f"  [Neo4j Data] Ejemplo del primer nodo extraído: {muestra}...")
                                elif "error" in data:
                                    print(f"  [Error] {data['error']}")
                                elif "accion_requerida" in data:
                                    print(f"  [Rechazo Cypher] El LLM intentó hacer trampa usando texto. Motivo: {data.get('error_validacion')}")
                            except Exception:
                                pass
                        elif msg.name == "describir_ontologia_ciar":
                            print("  [Razonamiento] El agente revisó la estructura completa de la ontología.")
                        elif msg.name == "resolver_entidad":
                            try:
                                data = json.loads(msg.content)
                                if "matches" in data:
                                    resumen = {lbl: [m.get("nombre") for m in hits] for lbl, hits in data["matches"].items()}
                                    print(f"  [Razonamiento] Entidad resuelta -> {resumen}")
                                else:
                                    print(f"  [Razonamiento] resolver_entidad: {data.get('resultado') or data.get('error')}")
                            except Exception:
                                pass
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
