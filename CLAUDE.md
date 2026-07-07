# Agente CIAR LangGraph — Instrucciones Locales

## Qué es
Agente de consola para consultar el grafo Neo4j del CIAR en lenguaje natural. Convierte preguntas en español a Cypher, valida la consulta, ejecuta solo lectura en Neo4j y redacta la respuesta.

## Fuente de verdad
- Primero manda el código actual de esta carpeta.
- Luego este `CLAUDE.md`, `sesiones/_index.md` y `sesiones/agente-langgraph.md`.
- No usar Supabase: este agente trabaja con Neo4j + LLMs.
- Usar el harness global desde `/Users/alejandromcht/CLAUDE.md` y `Obsidian Vault/AI_HARNESS.md`.

## Stack real
- Python
- LangGraph
- Neo4j driver
- LangChain Core
- `langchain-neo4j`
- `langchain-openai`
- `langchain-google-genai`
- `langchain-nvidia-ai-endpoints`
- `langchain-ollama`
- LangSmith disponible por dependencia

## Flujo del agente
`START → obtiene_pregunta → obtiene_grafo → resuelve_entidad → genera_cypher → valida_cypher → ejecuta_cypher → analiza_resultado → devuelve_resultado → END`

## Estructura clave
- `main.py` — loop de consola.
- `agent.py` — construye el grafo LangGraph.
- `estado.py` — `EstadoAgente`.
- `nodos/` — nodos del flujo.
- `utils/neo4j.py` — driver, introspección de schema vivo, validación y consultas de lectura.
- `utils/llm.py` — fábrica multi-proveedor con fallback.
- `prompts/` — prompts de resolución de entidad, generación Cypher y análisis de resultado.
- `PREGUNTAS_EJEMPLO.md` — casos manuales de prueba.
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
- LLM principal: `LLM_PROVIDER`
- Fallbacks: `LLM_FALLBACK`
- Modelos por proveedor: `OPENAI_MODEL`, `GEMINI_MODEL`, `NVIDIA_MODEL`, `OLLAMA_MODEL`

Proveedores soportados:
- `openai`
- `google_genai`
- `nvidia`
- `ollama`

## Verificación
- Activar el entorno si existe: `source .venv/bin/activate`
- Instalar deps si falta: `pip install -r requirements.txt`
- Ejecutar: `python main.py`
- Probar al menos una pregunta real contra Neo4j.
- Para cambios en prompts/generación Cypher, probar preguntas en `PREGUNTAS_EJEMPLO.md`.

## Memoria
- Índice: `sesiones/_index.md`
- Histórico principal: `sesiones/agente-langgraph.md`
- Registrar decisiones firmes o cambios de arquitectura vía el mecanismo global de Obsidian.
