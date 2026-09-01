"""Build the stateless CIAR graph with explicit security seams."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import cast
from uuid import uuid4

from langchain_core.runnables import RunnableConfig, RunnableLambda
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agente.grafo.estado import Estado
from agente.memoria_corta import (
    DEFAULT_CONVERSATION_MEMORY,
    ConversationMemory,
    server_memory_scope,
)
from agente.nodos.construye_cypher import construye_cypher
from agente.nodos.contextualiza_pregunta import contextualiza_pregunta
from agente.nodos.cypher_guard import cypher_guard
from agente.nodos.devuelve_respuesta import ReadQueryGateway, devuelve_respuesta
from agente.nodos.generar_cypher import GeneratedQueryRunnable
from agente.nodos.guarda_memoria_corta import guarda_memoria_corta
from agente.nodos.obtiene_pregunta import obtiene_pregunta
from agente.nodos.obtiene_schema import SchemaLoader, obtiene_schema
from agente.nodos.orquestador import OrchestratorRunnable, Route, orquestador
from agente.nodos.prompt_injection import contextualized_prompt_injection, prompt_injection
from agente.nodos.redacta_respuesta import AnalystRunnable, redacta_respuesta
from agente.nodos.responder_directo import DirectResponseRunnable, responder_directo
from agente.nodos.resuelve_entidades import resuelve_entidades
from agente.utils.logger import (
    attempt_context,
    log_error,
    log_event,
    node_logs_only_enabled,
    trace_context,
    trace_id,
)
from agente.utils.verbose import verbose_scope, verbose_step


def construir_grafo(
    *,
    orchestrator_runnable: OrchestratorRunnable | None = None,
    generated_runnable: GeneratedQueryRunnable | None = None,
    direct_runnable: DirectResponseRunnable | None = None,
    analyst_runnable: AnalystRunnable | None = None,
    schema_loader: SchemaLoader | None = None,
    cypher_gateway: ReadQueryGateway | None = None,
    entity_gateway: ReadQueryGateway | None = None,
    memory_store: ConversationMemory = DEFAULT_CONVERSATION_MEMORY,
) -> CompiledStateGraph[Estado, None, Estado, Estado]:
    """Compile one isolated request graph without a checkpointer."""
    builder = StateGraph(Estado)

    def state_keys(value: object) -> list[str]:
        if not isinstance(value, dict):
            return []
        return sorted(
            key
            for key in value
            if isinstance(key, str)
        )

    def state_size(value: object) -> int:
        return len(value) if isinstance(value, dict) else 0

    def node_status(input_state: Estado, output_state: Estado) -> str:
        """Classify a boundary without treating a node-produced error as success."""
        if input_state.get("error"):
            return "skipped"
        return "failed" if output_state.get("error") else "success"

    def run_sync_node(step: str, function: Callable[[Estado], Estado], estado: Estado) -> Estado:
        current_trace = estado.get("trace_id")
        with trace_context(
            current_trace if isinstance(current_trace, str) else None
        ) as active_trace:
            started_at = time.perf_counter()
            verbose_step("graph", f"Inicio nodo: {step}")
            log_event(
                "graph",
                "node_started",
                step=step,
                input_keys=state_keys(estado),
                input_size=state_size(estado),
                node_input=estado,
            )
            try:
                result = function(estado)
            except Exception as exc:
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                verbose_step(
                    "graph",
                    f"Nodo falló: {step}",
                    str(exc),
                    duration_ms=duration_ms,
                )
                log_error(
                    "graph",
                    "node_failed",
                    exc,
                    step=step,
                    status="failed",
                    duration_ms=duration_ms,
                    input_keys=state_keys(estado),
                    node_input=estado,
                )
                raise
            output = dict(result)
            output.setdefault("trace_id", active_trace)
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            verbose_step("graph", f"Fin nodo: {step}", duration_ms=duration_ms)
            log_event(
                "graph",
                "node_completed",
                step=step,
                status=node_status(estado, output),
                duration_ms=duration_ms,
                input_keys=state_keys(estado),
                output_keys=state_keys(output),
                output_size=state_size(output),
                # The start event already contains the input. Avoid serializing
                # the accumulated state a second time in the completion event.
                node_output=output,
            )
            return cast(Estado, output)

    async def run_async_node(
        step: str,
        function: Callable[[Estado], Awaitable[Estado]],
        estado: Estado,
    ) -> Estado:
        current_trace = estado.get("trace_id")
        with trace_context(
            current_trace if isinstance(current_trace, str) else None
        ) as active_trace:
            started_at = time.perf_counter()
            verbose_step("graph", f"Inicio nodo: {step}")
            log_event(
                "graph",
                "node_started",
                step=step,
                input_keys=state_keys(estado),
                input_size=state_size(estado),
                node_input=estado,
            )
            try:
                result = await function(estado)
            except Exception as exc:
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                verbose_step(
                    "graph",
                    f"Nodo falló: {step}",
                    str(exc),
                    duration_ms=duration_ms,
                )
                log_error(
                    "graph",
                    "node_failed",
                    exc,
                    step=step,
                    status="failed",
                    duration_ms=duration_ms,
                    input_keys=state_keys(estado),
                    node_input=estado,
                )
                raise
            output = dict(result)
            output.setdefault("trace_id", active_trace)
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            verbose_step("graph", f"Fin nodo: {step}", duration_ms=duration_ms)
            log_event(
                "graph",
                "node_completed",
                step=step,
                status=node_status(estado, output),
                duration_ms=duration_ms,
                input_keys=state_keys(estado),
                output_keys=state_keys(output),
                output_size=state_size(output),
                # The start event already contains the input. Avoid serializing
                # the accumulated state a second time in the completion event.
                node_output=output,
            )
            return cast(Estado, output)

    def question_node(estado: Estado) -> Estado:
        return run_sync_node("obtiene_pregunta", obtiene_pregunta, estado)

    builder.add_node("obtiene_pregunta", RunnableLambda(question_node))

    def prompt_injection_node(estado: Estado) -> Estado:
        return run_sync_node("prompt_injection", prompt_injection, estado)

    builder.add_node("prompt_injection", RunnableLambda(prompt_injection_node))

    def contextualization_node(estado: Estado) -> Estado:
        return run_sync_node(
            "contextualiza_pregunta",
            lambda value: contextualiza_pregunta(value, memory_store=memory_store),
            estado,
        )

    builder.add_node("contextualiza_pregunta", RunnableLambda(contextualization_node))

    def contextualized_prompt_injection_node(estado: Estado) -> Estado:
        return run_sync_node(
            "contextualized_prompt_injection",
            contextualized_prompt_injection,
            estado,
        )

    builder.add_node(
        "contextualized_prompt_injection",
        RunnableLambda(contextualized_prompt_injection_node),
    )

    async def orchestrator_node(estado: Estado) -> Estado:
        return await run_async_node(
            "orquestador",
            lambda value: orquestador(
                value,
                orchestrator_runnable=orchestrator_runnable,
            ),
            estado,
        )

    builder.add_node("orquestador", RunnableLambda(orchestrator_node))

    async def direct_response_node(estado: Estado) -> Estado:
        if isinstance(estado.get("respuesta"), str) and estado["respuesta"]:
            # Keep the skipped branch visible in the per-node trace.
            return run_sync_node("responder_directo", lambda _value: {}, estado)
        return await run_async_node(
            "responder_directo",
            lambda value: responder_directo(value, direct_runnable=direct_runnable),
            estado,
        )

    builder.add_node("responder_directo", RunnableLambda(direct_response_node))

    async def schema_node(estado: Estado) -> Estado:
        return await run_async_node(
            "obtiene_schema",
            lambda value: obtiene_schema(value, schema_loader=schema_loader),
            estado,
        )

    builder.add_node("obtiene_schema", RunnableLambda(schema_node))

    async def cypher_node(estado: Estado) -> Estado:
        return await run_async_node(
            "construye_cypher",
            lambda value: construye_cypher(value, generated_runnable=generated_runnable),
            estado,
        )

    builder.add_node("construye_cypher", RunnableLambda(cypher_node))

    async def entity_resolution_node(estado: Estado) -> Estado:
        return await run_async_node(
            "resuelve_entidades",
            lambda value: resuelve_entidades(
                value,
                entity_gateway=entity_gateway or cypher_gateway,
            ),
            estado,
        )

    builder.add_node("resuelve_entidades", RunnableLambda(entity_resolution_node))

    def cypher_guard_node(estado: Estado) -> Estado:
        return run_sync_node("cypher_guard", cypher_guard, estado)

    builder.add_node("cypher_guard", RunnableLambda(cypher_guard_node))

    async def response_node(estado: Estado) -> Estado:
        return await run_async_node(
            "devuelve_respuesta",
            lambda value: devuelve_respuesta(value, query_gateway=cypher_gateway),
            estado,
        )

    builder.add_node("devuelve_respuesta", RunnableLambda(response_node))

    async def grounded_response_node(estado: Estado) -> Estado:
        return await run_async_node(
            "redacta_respuesta",
            lambda value: redacta_respuesta(
                value,
                analyst_runnable=analyst_runnable,
            ),
            estado,
        )

    builder.add_node("redacta_respuesta", RunnableLambda(grounded_response_node))

    def memory_node(estado: Estado) -> Estado:
        return run_sync_node(
            "guarda_memoria_corta",
            lambda value: guarda_memoria_corta(value, memory_store=memory_store),
            estado,
        )

    builder.add_node("guarda_memoria_corta", RunnableLambda(memory_node))

    def route_after_orchestrator(estado: Estado) -> Route:
        if estado.get("error"):
            return "finalizar"
        ruta = estado.get("ruta")
        if ruta in {"conversacion", "cypher"}:
            return cast(Route, ruta)
        return "finalizar"

    builder.add_edge(START, "obtiene_pregunta")
    builder.add_edge("obtiene_pregunta", "prompt_injection")
    builder.add_edge("prompt_injection", "contextualiza_pregunta")
    builder.add_edge("contextualiza_pregunta", "contextualized_prompt_injection")
    builder.add_edge("contextualized_prompt_injection", "orquestador")
    builder.add_conditional_edges(
        "orquestador",
        route_after_orchestrator,
        {
            "conversacion": "responder_directo",
            "cypher": "obtiene_schema",
            "finalizar": "guarda_memoria_corta",
        },
    )
    builder.add_edge("responder_directo", "guarda_memoria_corta")
    builder.add_edge("obtiene_schema", "construye_cypher")
    builder.add_edge("construye_cypher", "resuelve_entidades")
    builder.add_edge("resuelve_entidades", "cypher_guard")
    builder.add_edge("cypher_guard", "devuelve_respuesta")
    builder.add_edge("devuelve_respuesta", "redacta_respuesta")
    builder.add_edge("redacta_respuesta", "guarda_memoria_corta")
    builder.add_edge("guarda_memoria_corta", END)
    return builder.compile()


def langgraph_entrypoint() -> CompiledStateGraph[Estado, None, Estado, Estado]:
    """Expose the stateless graph factory used by LangGraph's platform loader."""
    return construir_grafo()


async def responder(
    pregunta: str,
    *,
    user_id: str | None = None,
    thread_id: str | None = None,
    verbose: bool = False,
    memory_store: ConversationMemory = DEFAULT_CONVERSATION_MEMORY,
) -> str:
    """Run one isolated request while retaining the public correlation thread ID."""
    started_at = time.perf_counter()
    conversation_id = thread_id or str(uuid4())
    memory_scope = server_memory_scope(user_id or "internal-anonymous", conversation_id)
    config: RunnableConfig = {"configurable": {"thread_id": conversation_id}}
    with (
        trace_context(trace_id()) as active_trace,
        attempt_context(1),
        verbose_scope(verbose and not node_logs_only_enabled()),
    ):
        verbose_step("request", "Solicitud recibida", f"input_size={len(pregunta)}")
        log_event("graph", "request_started", input_keys=["pregunta"], input_size=len(pregunta))
        try:
            graph = (
                construir_grafo()
                if memory_store is DEFAULT_CONVERSATION_MEMORY
                else construir_grafo(memory_store=memory_store)
            )
            async with memory_store.serialized_scope(memory_scope):
                resultado = await graph.ainvoke(
                    {
                        "pregunta": pregunta,
                        "memory_scope": memory_scope,
                        "trace_id": active_trace,
                    },
                    config=config,
                )
        except Exception as exc:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            verbose_step("request", "Solicitud falló", str(exc), duration_ms=duration_ms)
            log_error(
                "graph",
                "request_failed",
                exc,
                status="failed",
                duration_ms=duration_ms,
            )
            raise
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        verbose_step("request", "Solicitud completada", duration_ms=duration_ms)
        log_event(
            "graph",
            "request_completed",
            duration_ms=duration_ms,
            status="degraded" if resultado.get("error") else "success",
            output_keys=sorted(resultado),
            output_size=len(resultado),
        )
        respuesta = resultado.get("respuesta")
        return respuesta if isinstance(respuesta, str) else "Sin respuesta aún"
