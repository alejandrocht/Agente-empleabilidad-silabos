# CIAR LangGraph Agent - Local Instructions

## Purpose

CIAR is a read-only Neo4j agent. It turns Spanish questions into safe Cypher-backed
answers about the academic and employment graph. OpenAI is the only supported LLM
provider.

## Source of truth

1. The current code in this repository.
2. This file and `AGENTS.md`.
3. Historical material in `sesiones/` and the Obsidian vault, only when it does not
   contradict the code or the live schema contract.

Do not restore the deleted `backend/src/agente` package or the deleted strategic-query
runner. The active package is `backend/agente`.

## Stack and active layout

- Python, LangGraph, LangChain Core, `langchain-openai`, Neo4j driver, FastAPI.
- OpenAI is the only LLM provider.
- `backend/agente/grafo/constructor.py` builds the graph and exposes `responder` for
  the console/API plus `langgraph_entrypoint` for LangGraph's no-argument graph loader.
- `backend/api/servidor.py` owns the HTTP boundary.
- `backend/agente/utils/db.py` is the guarded, read-only domain query gateway.
- `backend/agente/utils/neo4j_saver.py` owns LangGraph checkpoint lifecycle.
- `backend/agente/utils/neo4j_long_term_memory.py` owns durable user-scoped memory.
- `backend/agente/utils/tooler.py` contains the immutable 20-template catalog.
- `backend/agente/cache/consultas.py` contains the bounded process-local query-result cache.
- `backend/agente/memoria/` contains bounded short-term conversational context and
  deterministic 12-turn compaction.
- `backend/agente/utils/response_inspector.py` is always-on deterministic response
  inspection; there is no active inspector LLM switch.

## Active graph flow

`START -> obtiene_pregunta -> prompt_injection -> contextualiza_pregunta -> contextualized_prompt_injection -> orquestador -> (responder_directo | obtiene_schema -> construye_cypher -> resuelve_entidades -> cypher_guard -> devuelve_respuesta) -> guarda_memoria_corta -> END`

The `orquestador` route sends greetings, capability questions, and non-domain
conversation to `responder_directo`. Only questions that require academic or
employment facts continue to schema loading and Cypher generation. All domain
Cypher is guarded, executed with Neo4j `READ` routing, and bounded. No public
endpoint accepts arbitrary Cypher.

## Configuration

### Neo4j

- Domain reads prefer a complete `NEO4J_READ_URI`, `NEO4J_READ_USER`,
  `NEO4J_READ_PASSWORD` group and fall back as a whole to `NEO4J_URI`, `NEO4J_USER`,
  `NEO4J_PASSWORD`.
- LangGraph checkpoints prefer a complete `NEO4J_CHECKPOINT_URI`,
  `NEO4J_CHECKPOINT_USER`, `NEO4J_CHECKPOINT_PASSWORD` group and fall back as a whole
  to the legacy `NEO4J_*` group. Partial higher-priority groups fail closed.
- Durable memory selects complete groups in this order: `NEO4J_MEMORY_*`,
  `NEO4J_CHECKPOINT_*`, then `NEO4J_*`.
- `NEO4J_DATABASE`, `NEO4J_READ_DATABASE`, and `NEO4J_SCHEMA_CACHE_TTL_SECONDS`
  configure database reads and schema caching. See `backend/.env.example` for the
  complete template.

### OpenAI and runtime limits

- Shared fallback: `OPENAI_API_KEY`, `OPENAI_MODEL`, and optional `OPENAI_BASE_URL`.
- Role-specific models: `OPENAI_MODEL_PLANIFICADOR`, `OPENAI_MODEL_RESPONDER_DIRECTO`,
  `OPENAI_MODEL_GENERADOR_CYPHER`, `OPENAI_MODEL_FORMATEADOR`, and
  `OPENAI_MEMORY_MODEL`.
- Role-specific reasoning settings use the corresponding
  `OPENAI_REASONING_EFFORT_*` variables.
- Short-term context uses `MEMORIA_TTL_SEGUNDOS` and `MEMORIA_MAX_THREADS`.
- Query results use `QUERY_RESULT_CACHE_TTL_SECONDS` and
  `QUERY_RESULT_CACHE_MAX_ENTRIES`.
- Durable memory uses `CIAR_MEMORY_RECENT_LIMIT` and
  `CIAR_MEMORY_TIMEOUT_SECONDS`.
- Logging uses `CIAR_LOG_LEVEL` or the `LOG_LEVEL` fallback.
- `ANONYMOUS_ID_SECRET` signs the anonymous identity cookie.

## HTTP endpoints

- `GET /health`
- `POST /chat`
- `POST /chat/stream`
- `POST /preguntar`
- `GET /dashboard/metadata`
- `GET /dashboard/filtros/carreras`
- `GET /dashboard/ofertas/tendencia`
- `GET /dashboard/carreras/demanda`
- `GET /dashboard/carreras/{carrera_id}/industrias`
- `GET /dashboard/empresas`
- `GET /dashboard/dimensiones/{tipo}/demanda`
- `GET /dashboard/dimensiones/{tipo}/cobertura`
- `GET /dashboard/dimensiones/{tipo}/brechas`
- `GET /dashboard/dimensiones/{tipo}/industrias`

Dashboard filters are typed identifiers, dates, dimensions, and limits. The active
dashboard supports trend, career demand, industries by career, knowledge demand,
curriculum coverage, demand gaps, and company ranking. The five datasets listed in
`UNSUPPORTED_DATASETS` remain deferred until validated projections exist in the active
schema; they must not be represented with graph data or hidden mocks.

## Normalizador curricular
- Toda ejecución real de sílabos debe pasar por el analista LLM curricular; mantener `NORMALIZADOR_CURRICULAR_LLM=true` en `backend/.env`.
- El flujo semántico divide los logros en lotes de 8, conserva cache y publica `analisis_llm.json` y `decisiones_llm.jsonl` como evidencia.
- No considerar `limpios/silabos.jsonl` como resultado final: es staging previo al análisis LLM.
- `NORMALIZADOR_CURRICULAR_INSPECTOR=true` debe mantenerse activo para revisar las decisiones del analista.
- El valor `NORMALIZADOR_CURRICULAR_LLM=false` solo es válido en pruebas offline explícitas; no usarlo para ejecuciones reales ni para smoke tests del producto.
- `NORMALIZADOR_CATALOGOS_DIR` apunta al catálogo CHH externo; una ejecución real no debe sustituirlo por datos inventados.

## Verificación
- Instalar el paquete: `cd backend && python -m pip install -e ".[dev]"`.
- Ejecutar el agente: `cd backend && python scripts/consola.py`.
- Ejecutar la API: `cd backend && python -m uvicorn api.servidor:app --reload --port 8001`.
- Calidad: `cd backend && python -m ruff check . && python -m mypy agente api && python -m pytest -q`.
- Compilación: `cd backend && python -m compileall -q agente api scripts`.
- Frontend: `cd frontend && npm run check && npm audit --omit=dev`.
- Probar al menos una pregunta real contra Neo4j.
- Para cambios en prompts/generación Cypher, probar preguntas en `backend/PREGUNTAS_EJEMPLO.md`.

## Memoria
- Índice: `sesiones/_index.md`
- Histórico principal: `sesiones/agente-langgraph.md`
- Registrar decisiones firmes o cambios de arquitectura vía el mecanismo global de Obsidian.
Live-only acceptance is separate and is not part of offline verification: a real
Neo4j question, Neo4j `EXPLAIN`/execution against the deployed schema, and external
OpenAI/LangSmith connectivity. Never run those checks with placeholder credentials.
