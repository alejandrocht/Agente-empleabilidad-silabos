import asyncio
import hashlib
import hmac
import json
import math
import os
import secrets
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from datetime import date
from typing import Any, TypeVar, cast
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from agente import responder
from agente.api.neo4j_importacion import router as neo4j_importacion_router
from agente.api.normalizador import router as normalizador_router
from agente.dashboard import servicio as dashboard
from agente.grafo.constructor import construir_grafo
from agente.memoria_corta import DEFAULT_CONVERSATION_MEMORY, server_memory_scope
from agente.utils.cypher_guard import CypherGuardError, guard_cypher
from agente.utils.logger import (
    attempt_context,
    configure_node_log_scope,
    log_error,
    log_event,
    trace_context,
)
from agente.utils.validacion import EntradaInvalida, validar_pregunta

USER_FACING_STREAM_NODES: frozenset[str] = frozenset(
    {"redacta_respuesta", "responder_directo"}
)
DEFAULT_GRAPH_TIMEOUT_SECONDS = 90.0
GRAPH_TIMEOUT_RESPONSE = (
    "La consulta tardó más de lo esperado y fue detenida de forma segura. "
    "Intentá nuevamente o formulala de manera más específica."
)
PUBLIC_TEXT_FIELDS = ("respuesta", "error")
PUBLIC_PHASES = frozenset(
    {
        "analizando",
        "preparando_consulta",
        "validando_consulta",
        "consultando_grafo",
        "redactando",
        "completado",
    }
)
MAX_PUBLIC_CYPHER_CHARS = 12_000
TEXT_BLOCK_TYPES = frozenset({"text", "output_text"})
STREAM_PHASE_BY_NODE = {
    "obtiene_pregunta": "analizando",
    "prompt_injection": "analizando",
    "orquestador": "analizando",
    "obtiene_schema": "preparando_consulta",
    "construye_cypher": "preparando_consulta",
    "resuelve_entidades": "preparando_consulta",
    "cypher_guard": "validando_consulta",
    "devuelve_respuesta": "consultando_grafo",
    "redacta_respuesta": "redactando",
    "responder_directo": "redactando",
    "LangGraph": "completado",
}
STREAM_PROGRESS_BY_NODE = {
    "obtiene_pregunta": "Recibiendo tu pregunta…",
    "prompt_injection": "Validando la entrada…",
    "orquestador": "Entendiendo tu solicitud…",
    "obtiene_schema": "Preparando la información…",
    "construye_cypher": "Preparando la consulta…",
    "resuelve_entidades": "Identificando los conceptos clave…",
    "cypher_guard": "Verificando la consulta…",
    "devuelve_respuesta": "Buscando la información…",
    "redacta_respuesta": "Escribiendo la respuesta…",
    "responder_directo": "Preparando la respuesta…",
}
STREAM_TOKEN_PROGRESS_BY_NODE = {
    "orquestador": "Analizando la intención…",
    "construye_cypher": "Diseñando la consulta…",
    "responder_directo": "Escribiendo la respuesta…",
    "redacta_respuesta": "Escribiendo la respuesta…",
}
_UNSAFE_VALUE = object()
ANONYMOUS_ID_COOKIE = "ciar_anon_identity"
_ANONYMOUS_ID_MAX_AGE = 60 * 60 * 24 * 30
_ANONYMOUS_SIGNING_SECRET = secrets.token_bytes(32)

# Apply the operator-selected node-only scope before Uvicorn starts serving requests.
configure_node_log_scope()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log_event("api", "started")
    try:
        yield
    finally:
        log_event("api", "stopped")


app = FastAPI(title="Agente CIAR", lifespan=lifespan)
app.include_router(normalizador_router, prefix="/normalizador", tags=["normalizador"])
app.include_router(neo4j_importacion_router, prefix="/neo4j", tags=["neo4j-importacion"])


class Pregunta(BaseModel):
    texto: str
    thread_id: str | None = None


class PreguntaChat(BaseModel):
    pregunta: str
    id_sesion: str | None = None
    thread_id: str | None = None


class Respuesta(BaseModel):
    respuesta: str
    thread_id: str


class ChatStreamBody(BaseModel):
    input: dict[str, object]
    config: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] | None = None
    command: dict[str, Any] | None = None


DashboardResult = TypeVar("DashboardResult")


def _validate_public_question(value: object, route: str) -> str:
    """Apply the shared input guard before allocating graph resources."""
    log_event("api", "validation_started", route=route)
    try:
        validated = validar_pregunta(value)
    except EntradaInvalida as exc:
        log_event(
            "api",
            "request_rejected",
            route=route,
            reason=exc.tipo,
            status="failed",
            level="warning",
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    log_event(
        "api",
        "validation_completed",
        route=route,
        status="success",
        length=len(validated),
    )
    return validated


def _graph_timeout_seconds() -> float:
    """Return a positive whole-graph deadline without trusting bad config."""
    raw_value = os.getenv("CIAR_GRAPH_TIMEOUT_SECONDS")
    if raw_value is None:
        return DEFAULT_GRAPH_TIMEOUT_SECONDS
    try:
        value = float(raw_value)
    except ValueError:
        return DEFAULT_GRAPH_TIMEOUT_SECONDS
    return value if math.isfinite(value) and value > 0 else DEFAULT_GRAPH_TIMEOUT_SECONDS


def extract_public_text(content: object) -> str:
    """Extract only explicit text blocks from a chat-model stream chunk."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") not in TEXT_BLOCK_TYPES:
            continue
        text = block.get("text")
        if not isinstance(text, str):
            text = block.get("content")
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def _stream_text_from_event(event: dict[str, Any]) -> str:
    """Return text only when LangGraph attributes the model event to a public node."""
    if _stream_node_from_event(event) not in USER_FACING_STREAM_NODES:
        return ""

    data = event.get("data")
    if not isinstance(data, dict):
        return ""
    chunk = data.get("chunk")
    return extract_public_text(getattr(chunk, "content", ""))


def _stream_node_from_event(event: dict[str, Any]) -> str:
    """Resolve the graph node without exposing callback or model names."""
    metadata = event.get("metadata")
    node = metadata.get("langgraph_node") if isinstance(metadata, dict) else None
    if isinstance(node, str):
        return node
    name = event.get("name")
    return name if isinstance(name, str) else ""


def _stream_phase_from_event(event: dict[str, Any]) -> str:
    """Map internal graph events to a small, user-facing progress vocabulary."""
    node = _stream_node_from_event(event)
    if node == "LangGraph" and event.get("event") != "on_chain_end":
        return ""
    phase = STREAM_PHASE_BY_NODE.get(node) if isinstance(node, str) else None
    return phase if isinstance(phase, str) and phase in PUBLIC_PHASES else ""


def stream_progress_event(text: str, phase: str) -> str:
    """Serialize one user-facing progress event for the LangGraph SDK."""
    payload = {"type": "progress", "fase": phase, "texto": text}
    return f"event: custom\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def stream_message_event(message_id: str, node: str, content: str) -> str:
    """Serialize a token using the native LangGraph ``messages`` protocol."""
    payload = [
        {"type": "ai", "id": message_id, "content": content},
        {"langgraph_node": node},
    ]
    return f"event: messages\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _validated_public_cypher(output: Mapping[str, object]) -> str | None:
    """Expose only a query that the same read-only guard has accepted."""
    cypher = output.get("cypher")
    parameters = output.get("parameters")
    if not isinstance(cypher, str) or not isinstance(parameters, Mapping):
        return None
    try:
        guarded = guard_cypher(cypher, parameters)
    except (CypherGuardError, TypeError, ValueError):
        return None
    if len(guarded.text) > MAX_PUBLIC_CYPHER_CHARS:
        return None
    return guarded.text


def sanitize_public_state(output: object) -> dict[str, object]:
    """Project LangGraph state onto the JSON-safe public SSE contract."""
    if not isinstance(output, dict):
        return {}

    public_state: dict[str, object] = {}
    for field in PUBLIC_TEXT_FIELDS:
        value = output.get(field, _UNSAFE_VALUE)
        if value is None or isinstance(value, str):
            public_state[field] = value
    if isinstance(output, Mapping):
        cypher = _validated_public_cypher(output)
        if cypher is not None:
            public_state["cypher"] = cypher
        phase = output.get("fase")
        if isinstance(phase, str) and phase in PUBLIC_PHASES:
            public_state["fase"] = phase
    return public_state


def _thread_id(candidate: str | None) -> str:
    """Use a client thread UUID when valid; mint one for new or legacy clients."""
    if isinstance(candidate, str) and candidate:
        candidate = candidate.removeprefix("sesion-")
        try:
            return str(UUID(candidate))
        except (ValueError, AttributeError, TypeError):
            pass
    return str(uuid4())


def _sign_anonymous_identity(identity: str) -> str:
    signature = hmac.new(
        _ANONYMOUS_SIGNING_SECRET,
        identity.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{identity}.{signature}"


def _anonymous_identity(request: Request) -> tuple[str, str | None]:
    """Trust only a valid HttpOnly server-signed anonymous identity cookie."""
    value = request.cookies.get(ANONYMOUS_ID_COOKIE)
    if isinstance(value, str):
        identity, separator, signature = value.rpartition(".")
        expected = hmac.new(
            _ANONYMOUS_SIGNING_SECRET,
            identity.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if separator and identity and hmac.compare_digest(signature, expected):
            return identity, None
    identity = secrets.token_urlsafe(24)
    return identity, _sign_anonymous_identity(identity)


def _set_anonymous_cookie(
    response: JSONResponse | StreamingResponse,
    request: Request,
    value: str | None,
) -> None:
    if value is None:
        return
    response.set_cookie(
        ANONYMOUS_ID_COOKIE,
        value,
        max_age=_ANONYMOUS_ID_MAX_AGE,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )


async def _memory_serialized_events(
    graph: Any,
    state: dict[str, Any],
    config: RunnableConfig,
    memory_scope: str,
) -> AsyncIterator[dict[str, Any]]:
    """Hold the per-scope gate until the streaming graph cycle is complete."""
    async with DEFAULT_CONVERSATION_MEMORY.serialized_scope(memory_scope):
        stream = graph.astream_events(
            cast(Any, state),
            config=config,
            version="v2",
        )
        async for event in cast(AsyncIterator[dict[str, Any]], stream):
            yield event


async def _bounded_memory_serialized_events(
    graph: Any,
    state: dict[str, Any],
    config: RunnableConfig,
    memory_scope: str,
    timeout_seconds: float,
) -> AsyncIterator[dict[str, Any]]:
    """Stop a stalled graph while preserving the per-scope lock cleanup."""
    async with asyncio.timeout(timeout_seconds):
        async for event in _memory_serialized_events(graph, state, config, memory_scope):
            yield event


async def _dashboard_operation(
    name: str,
    operation: Callable[[], Awaitable[DashboardResult]],
) -> DashboardResult:
    """Map dashboard validation and provider failures to safe HTTP responses."""
    try:
        return await operation()
    except dashboard.ErrorDashboard as exc:
        log_error("api", "dashboard_rejected", exc, route=name)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log_error("api", "dashboard_failed", exc, route=name)
        raise HTTPException(
            status_code=503,
            detail="Dashboard data is temporarily unavailable.",
        ) from exc


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/dashboard/metadata")
async def dashboard_metadata() -> dict[str, Any]:
    return await _dashboard_operation("dashboard_metadata", dashboard.metadatos)


@app.get("/dashboard/filtros/carreras")
async def dashboard_carreras() -> dict[str, Any]:
    return await _dashboard_operation("dashboard_carreras", dashboard.listar_carreras)


@app.get("/dashboard/ofertas/tendencia")
async def dashboard_tendencia(
    desde: date = Query(...),
    hasta: date = Query(...),
    carrera_id: str | None = Query(default=None, min_length=1, max_length=128),
) -> dict[str, Any]:
    return await _dashboard_operation(
        "dashboard_tendencia",
        lambda: dashboard.tendencia_ofertas(desde, hasta, carrera_id),
    )


@app.get("/dashboard/carreras/demanda")
async def dashboard_carreras_demanda(
    desde: date = Query(...),
    hasta: date = Query(...),
    limite: int = Query(default=10, ge=1, le=dashboard.MAX_LIMITE),
) -> dict[str, Any]:
    return await _dashboard_operation(
        "dashboard_carreras_demanda",
        lambda: dashboard.carreras_por_demanda(desde, hasta, limite),
    )


@app.get("/dashboard/carreras/{carrera_id}/industrias")
async def dashboard_industrias_por_carrera(
    carrera_id: str,
    desde: date = Query(...),
    hasta: date = Query(...),
    limite: int = Query(default=10, ge=1, le=dashboard.MAX_LIMITE),
) -> dict[str, Any]:
    return await _dashboard_operation(
        "dashboard_industrias_por_carrera",
        lambda: dashboard.industrias_por_carrera(carrera_id, desde, hasta, limite),
    )


@app.get("/dashboard/empresas")
async def dashboard_empresas(
    desde: date = Query(...),
    hasta: date = Query(...),
    limite: int = Query(default=10, ge=1, le=dashboard.MAX_LIMITE),
) -> dict[str, Any]:
    return await _dashboard_operation(
        "dashboard_empresas",
        lambda: dashboard.empresas_dashboard(desde, hasta, limite),
    )


@app.get("/dashboard/dimensiones/{tipo}/demanda")
async def dashboard_demanda(
    tipo: str,
    carrera_id: str = Query(..., min_length=1, max_length=128),
    desde: date = Query(...),
    hasta: date = Query(...),
    limite: int = Query(default=10, ge=1, le=dashboard.MAX_LIMITE),
) -> dict[str, Any]:
    return await _dashboard_operation(
        "dashboard_demanda",
        lambda: dashboard.demanda_dimension(tipo, carrera_id, desde, hasta, limite),
    )


@app.get("/dashboard/dimensiones/{tipo}/cobertura")
async def dashboard_cobertura(
    tipo: str,
    carrera_id: str = Query(..., min_length=1, max_length=128),
    limite: int = Query(default=10, ge=1, le=dashboard.MAX_LIMITE),
) -> dict[str, Any]:
    return await _dashboard_operation(
        "dashboard_cobertura",
        lambda: dashboard.cobertura_dimension(tipo, carrera_id, limite),
    )


@app.get("/dashboard/dimensiones/{tipo}/brechas")
async def dashboard_brechas(
    tipo: str,
    carrera_id: str = Query(..., min_length=1, max_length=128),
    desde: date = Query(...),
    hasta: date = Query(...),
    limite: int = Query(default=10, ge=1, le=dashboard.MAX_LIMITE),
) -> dict[str, Any]:
    return await _dashboard_operation(
        "dashboard_brechas",
        lambda: dashboard.brechas_dimension(tipo, carrera_id, desde, hasta, limite),
    )


@app.get("/dashboard/dimensiones/{tipo}/industrias")
async def dashboard_industrias(
    tipo: str,
    elemento_id: str = Query(..., min_length=1, max_length=128),
    desde: date = Query(...),
    hasta: date = Query(...),
    limite: int = Query(default=10, ge=1, le=dashboard.MAX_LIMITE),
) -> dict[str, Any]:
    return await _dashboard_operation(
        "dashboard_industrias",
        lambda: dashboard.industrias_elemento(tipo, elemento_id, desde, hasta, limite),
    )


@app.post("/chat", response_model=Respuesta)
async def chat(body: PreguntaChat, request: Request) -> JSONResponse:
    with trace_context(), attempt_context(1):
        started_at = time.perf_counter()
        log_event(
            "api",
            "request_started",
            route="chat",
            input_keys=["pregunta", "thread_id"],
            status="structured",
        )
        pregunta = _validate_public_question(body.pregunta, "chat")

        thread_id = _thread_id(body.thread_id or body.id_sesion)
        user_identity, new_identity_cookie = _anonymous_identity(request)
        try:
            resultado = await asyncio.wait_for(
                responder(
                    pregunta,
                    user_id=user_identity,
                    thread_id=thread_id,
                    memory_store=DEFAULT_CONVERSATION_MEMORY,
                ),
                timeout=_graph_timeout_seconds(),
            )
        except TimeoutError as exc:
            log_error("api", "request_timeout", exc, route="chat", status="degraded")
            resultado = GRAPH_TIMEOUT_RESPONSE
        except EntradaInvalida as exc:
            log_error("api", "request_rejected", exc, route="chat", status="failed")
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            log_error(
                "api",
                "request_failed",
                exc,
                route="chat",
                status="failed",
                duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            )
            raise

        response = JSONResponse({"respuesta": resultado, "thread_id": thread_id})
        _set_anonymous_cookie(response, request, new_identity_cookie)
        log_event(
            "api",
            "response_emitted",
            route="chat",
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            status="success",
            output_keys=["respuesta", "thread_id"],
            output_size=len(resultado),
        )
        return response
@app.post("/chat/stream")
async def chat_stream(body: ChatStreamBody, request: Request) -> StreamingResponse:
    with trace_context() as active_trace, attempt_context(1):
        started_at = time.perf_counter()
        log_event(
            "api",
            "request_started",
            route="chat_stream",
            input_keys=["input", "config"],
            status="structured",
        )
        pregunta = _validate_public_question(body.input.get("pregunta"), "chat_stream")

        configurable = dict(body.config.get("configurable", {}))
        thread_id = _thread_id(configurable.get("thread_id"))
        user_identity, new_identity_cookie = _anonymous_identity(request)
        memory_scope = server_memory_scope(user_identity, thread_id)
        configurable.pop("user_id", None)
        configurable.pop("memory_scope", None)
        configurable["thread_id"] = thread_id
        runnable_config = cast(
            RunnableConfig,
            {**body.config, "configurable": configurable},
        )
        stream_status = "success"

        async def generate() -> AsyncIterator[str]:
            nonlocal stream_status
            with trace_context(active_trace), attempt_context(1):
                public_state: dict[str, Any] = {}
                last_progress = ""
                answer_started = False
                message_ids: dict[str, str] = {}

                def emit_values() -> str:
                    ordered_state: dict[str, Any] = {}
                    for key in ("respuesta", "cypher", "error", "fase"):
                        if key in public_state:
                            ordered_state[key] = public_state[key]
                    for key, value in public_state.items():
                        if key not in ordered_state:
                            ordered_state[key] = value
                    payload = json.dumps(ordered_state, ensure_ascii=False)
                    return f"event: values\ndata: {payload}\n\n"

                def emit_progress(node: str, *, from_model: bool = False) -> str | None:
                    nonlocal last_progress
                    progress_map = (
                        STREAM_TOKEN_PROGRESS_BY_NODE
                        if from_model
                        else STREAM_PROGRESS_BY_NODE
                    )
                    progress = progress_map.get(node)
                    if not progress or progress == last_progress:
                        return None
                    phase = STREAM_PHASE_BY_NODE.get(node)
                    if phase not in PUBLIC_PHASES:
                        return None
                    last_progress = progress
                    return stream_progress_event(progress, phase)

                def update_public_state(output: object, phase: str = "") -> bool:
                    if not isinstance(output, dict):
                        return False
                    sanitized = sanitize_public_state(output)
                    sanitized.pop("respuesta", None)
                    if sanitized.get("error") is None:
                        sanitized.pop("error", None)
                    if phase:
                        sanitized["fase"] = phase
                    previous_state = dict(public_state)
                    public_state.update(sanitized)
                    return public_state != previous_state

                try:
                    yield stream_progress_event("Analizando tu consulta…", "analizando")
                    last_progress = "Analizando tu consulta…"
                    graph = construir_grafo()
                    async for event in _bounded_memory_serialized_events(
                        graph,
                        {
                            "pregunta": pregunta,
                            "memory_scope": memory_scope,
                            "trace_id": active_trace,
                        },
                        runnable_config,
                        memory_scope,
                        _graph_timeout_seconds(),
                    ):
                        kind = event.get("event", "")
                        node = _stream_node_from_event(event)
                        phase = _stream_phase_from_event(event)
                        if kind == "on_chain_start":
                            progress_event = emit_progress(node)
                            if progress_event:
                                yield progress_event
                            continue

                        if kind == "on_chat_model_stream":
                            progress_event = emit_progress(node, from_model=True)
                            if progress_event:
                                yield progress_event
                            content = _stream_text_from_event(event)
                            if content:
                                answer_started = True
                                message_id = message_ids.setdefault(node, str(uuid4()))
                                yield stream_message_event(message_id, node, content)
                        elif kind == "on_chain_end":
                            data = event.get("data")
                            output = data.get("output", {}) if isinstance(data, dict) else {}
                            if isinstance(output, dict) and output.get("error"):
                                stream_status = "degraded"
                            sanitized = sanitize_public_state(output)
                            if node == "LangGraph":
                                sanitized["fase"] = "completado"
                                public_state.update(sanitized)
                                yield emit_values()
                                continue

                            if update_public_state(output, phase) and not answer_started:
                                yield emit_values()
                except TimeoutError as exc:
                    log_error(
                        "api",
                        "stream_timeout",
                        exc,
                        route="chat_stream",
                        status="degraded",
                    )
                    stream_status = "degraded"
                    public_state.clear()
                    public_state.update(
                        {
                            "respuesta": GRAPH_TIMEOUT_RESPONSE,
                            "error": "graph_timeout",
                            "fase": "completado",
                        }
                    )
                    yield emit_values()
                except EntradaInvalida as exc:
                    log_error("api", "stream_rejected", exc, route="chat_stream", status="failed")
                    yield f"event: error\ndata: {json.dumps({'error': str(exc)})}\n\n"
                except Exception as exc:
                    log_error(
                        "api",
                        "stream_failed",
                        exc,
                        route="chat_stream",
                        status="failed",
                        duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
                    )
                    stream_status = "degraded"
                    log_event("api", "stream_emission", route="chat_stream", emission="error")
                    yield "event: error\ndata: {\"error\": \"Error interno del servidor\"}\n\n"
                else:
                    log_event(
                        "api",
                        "stream_completed",
                        route="chat_stream",
                        duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
                        status=stream_status,
                        output_keys=sorted(public_state),
                    )
                log_event("api", "stream_emission", route="chat_stream", emission="end")
                yield "event: end\ndata: {}\n\n"

        response = StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "X-CIAR-Thread-ID": thread_id,
            },
        )
        _set_anonymous_cookie(response, request, new_identity_cookie)
        log_event(
            "api",
            "stream_opened",
            route="chat_stream",
            status="success",
            output_keys=["sse"],
        )
        return response


@app.post("/preguntar", response_model=Respuesta)
async def preguntar(pregunta: Pregunta, request: Request) -> JSONResponse:
    with trace_context(), attempt_context(1):
        started_at = time.perf_counter()
        log_event(
            "api",
            "request_started",
            route="preguntar",
            input_keys=["texto", "thread_id"],
            status="structured",
        )
        texto = _validate_public_question(pregunta.texto, "preguntar")

        thread_id = _thread_id(pregunta.thread_id)
        user_identity, new_identity_cookie = _anonymous_identity(request)
        try:
            resultado = await responder(
                texto,
                user_id=user_identity,
                thread_id=thread_id,
                memory_store=DEFAULT_CONVERSATION_MEMORY,
            )
        except EntradaInvalida as exc:
            log_error("api", "request_rejected", exc, route="preguntar", status="failed")
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            log_error(
                "api",
                "request_failed",
                exc,
                route="preguntar",
                status="failed",
                duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            )
            raise

        response = JSONResponse({"respuesta": resultado, "thread_id": thread_id})
        _set_anonymous_cookie(response, request, new_identity_cookie)
        log_event(
            "api",
            "response_emitted",
            route="preguntar",
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
            status="success",
            output_keys=["respuesta", "thread_id"],
            output_size=len(resultado),
        )
        return response
