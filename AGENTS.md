# CIAR — Agente Empleabilidad

## ¿Qué es?

Agente principal y objetivo final actual del proyecto CIAR. Convierte preguntas en español a Cypher, valida que sean de solo lectura, consulta Neo4j y redacta respuestas sobre datos académicos y de empleabilidad.

## Fuente de verdad

1. Código actual de esta carpeta.
2. `CLAUDE.md`.
3. `sesiones/_index.md` y la sesión relevante.
4. El vault de Obsidian solo como contexto de alto nivel.

## Stack real

- Python
- LangGraph
- Neo4j driver
- LangChain Core
- `langchain-openai`
- OpenAI como proveedor LLM único

## Reglas firmes

- Solo lectura en Neo4j
- No meter Supabase ni pgvector en este agente
- Mantener validación de schema y bloqueo de escrituras
- Si una nota contradice el código o el schema vivo, gana el código/schema

## Verificación

- `cd backend && python scripts/consola.py`
- Probar al menos una pregunta real contra Neo4j
- Si se toca generación/validación de Cypher, probar casos de `PREGUNTAS_EJEMPLO.md`
