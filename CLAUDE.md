# Agente CIAR LangGraph — Instrucciones Locales

## Qué es
Agente de consola para consultar el grafo Neo4j del CIAR en lenguaje natural. Convierte preguntas en español a Cypher, valida la consulta, ejecuta solo lectura en Neo4j y redacta la respuesta.

## Fuente de verdad
- Primero manda el código actual de esta carpeta.
- Luego este `CLAUDE.md`, `sesiones/_index.md` y `sesiones/agente-langgraph.md`.
- No usar Supabase: este agente trabaja con Neo4j + LLMs.

## Stack real
- Python
- LangGraph
- Neo4j driver
- LangChain Core
- `langchain-openai`
- LangSmith disponible por dependencia

## Flujo del agente
`START → obtiene_pregunta → obtiene_grafo → selecciona_estrategia → caché | plantilla | flujo dinámico → valida/ejecuta → analiza_resultado → devuelve_resultado → END`

## Estructura clave
```
proyecto/
├── backend/          ← todo el código Python del agente
│   ├── pyproject.toml — dependencias y configuración de calidad
│   ├── langgraph.json — factoría del grafo para LangGraph
│   ├── src/agente_ciar/ — paquete instalable con grafo, nodos, guardas y memoria
│   ├── scripts/consola.py — loop de consola
│   ├── tests/unit/   — pruebas aisladas
│   ├── tests/integration/ — auditoría del flujo
│   ├── .env          — variables de entorno (no versionado)
│   └── PREGUNTAS_EJEMPLO.md — casos manuales de prueba
├── frontend/         ← aplicación Next.js
└── sesiones/         — histórico técnico del agente
```
- `backend/src/agente_ciar/db/neo4j.py` — driver, schema vivo y transacciones de lectura.
- `backend/src/agente_ciar/guardas/cypher.py` — validador único de solo lectura.
- `backend/src/agente_ciar/llm/fabrica.py` — fábrica OpenAI con modelo por rol.
- `sesiones/agente-langgraph.md` — histórico técnico del agente.

## Reglas específicas
- Las consultas a Neo4j deben ser de solo lectura.
- No permitir `CREATE`, `MERGE`, `DELETE`, `SET`, `DROP`, `REMOVE`, `LOAD CSV`, `CALL dbms` ni escrituras.
- `valida_cypher` debe seguir bloqueando labels/relaciones inexistentes y validar sintaxis con `EXPLAIN`.
- Mantener `obtiene_grafo` alineado con el schema vivo de Neo4j.
- No depender de `nombre_norm`; el agente resuelve entidades contra Neo4j.
- No hardcodear schema si puede introspectarse.
- No meter Supabase ni pgvector en este agente.

## Configuración
El `.env` define:
- Neo4j: `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
- OpenAI: `OPENAI_API_KEY`, `OPENAI_MODEL`
- Modelos por rol: `OPENAI_MODEL_ENTIDAD`, `OPENAI_MODEL_CYPHER`, `OPENAI_MODEL_ANALISIS`, `OPENAI_MODEL_RESUMEN`, `OPENAI_MODEL_INSPECTOR`
- TTL y límite: `MEMORIA_TTL_SEGUNDOS`, `CACHE_TTL_SEGUNDOS`, `CACHE_MAX_ENTRADAS`

Proveedor soportado: solo `openai`.

## Verificación
- Instalar el paquete: `cd backend && python -m pip install -e ".[dev]"`
- Ejecutar el agente: `cd backend && python scripts/consola.py`
- Ejecutar la API: `cd backend && uvicorn agente_ciar.api.servidor:app --reload --port 8001`
- Calidad: `cd backend && python -m ruff check src tests scripts && python -m mypy src && python -m pytest`
- Frontend: `cd frontend && npm run check && npm audit --omit=dev`
- Probar al menos una pregunta real contra Neo4j.
- Para cambios en prompts/generación Cypher, probar preguntas en `backend/PREGUNTAS_EJEMPLO.md`.

## Memoria
- Índice: `sesiones/_index.md`
- Histórico principal: `sesiones/agente-langgraph.md`
- Registrar decisiones firmes o cambios de arquitectura vía el mecanismo global de Obsidian.
