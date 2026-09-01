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
- `backend/agente/memoria_corta.py` contains bounded process-local conversational context.
- `backend/agente/nodos/redacta_respuesta.py` asks the analyst model to explain verified rows.
- `backend/agente/cache/consultas.py` is used by the typed dashboard services, not the chat graph.
- `backend/agente/utils/response_inspector.py` validates grounded analyst output.

## Active graph flow

`START -> obtiene_pregunta -> prompt_injection -> orquestador -> (responder_directo | obtiene_schema -> construye_cypher -> resuelve_entidades -> cypher_guard -> devuelve_respuesta -> redacta_respuesta) -> guarda_memoria_corta -> END`

La contextualización automática de seguimientos (`contextualiza_pregunta` y
`contextualized_prompt_injection`) está desactivada temporalmente; el grafo usa la pregunta
original validada en cada turno.

The `orquestador` sends greetings, capability questions, and non-domain conversation to the
analyst. Questions requiring academic or employment facts continue to the Cypher generator.
With the current local configuration these roles use GPT-OSS 120B, GPT-OSS 20B, and Luna Max,
respectively. All domain Cypher is guarded, executed with Neo4j `READ` routing, and bounded.
Verified rows return to the analyst, with IDs removed unless explicitly requested. No public
endpoint accepts arbitrary Cypher.

## Configuration

### Neo4j

- Domain reads prefer a complete `NEO4J_READ_URI`, `NEO4J_READ_USER`,
  `NEO4J_READ_PASSWORD` group and fall back as a whole to `NEO4J_URI`, `NEO4J_USER`,
  `NEO4J_PASSWORD`.
- `NEO4J_DATABASE`, `NEO4J_READ_DATABASE`, and `NEO4J_SCHEMA_CACHE_TTL_SECONDS`
  configure database reads and schema caching. See `backend/.env.example` for the
  complete template.

### OpenAI and runtime limits

- Credentials and endpoint: `OPENAI_API_KEY` and optional `OPENAI_BASE_URL`.
- Conversational roles: `OPENAI_MODEL_ORQUESTADOR`,
  `OPENAI_MODEL_GENERADOR_CYPHER`, and `OPENAI_MODEL_ANALISTA`.
- Role-specific reasoning settings use the corresponding
  `OPENAI_REASONING_EFFORT_*` variables.
- Short-term chat context is process-local and bounded to four turns with a 30-minute TTL.
- Dashboard query results use `QUERY_RESULT_CACHE_TTL_SECONDS` and
  `QUERY_RESULT_CACHE_MAX_ENTRIES`.
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
