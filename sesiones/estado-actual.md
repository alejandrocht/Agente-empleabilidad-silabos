# Estado actual del proyecto — Agente CIAR

> Documento canónico del estado real. Actualizado: 2026-08-26.
> El código activo y el schema vivo prevalecen sobre notas históricas.

## Resumen ejecutivo

CIAR convierte preguntas en español en consultas Cypher de solo lectura sobre Neo4j y responde
con datos académicos y de empleabilidad. El proveedor LLM único es OpenAI. El backend usa
Python, LangGraph y FastAPI; el frontend usa Next.js.

El agente es funcional para demostración y uso controlado. Aún no incluye autenticación ni rate
limiting, y su memoria conversacional es local al proceso.

## Flujo activo

```text
START
  -> obtiene_pregunta
  -> prompt_injection
  -> orquestador
       -> responder_directo
       -> obtiene_schema
          -> construye_cypher
          -> resuelve_entidades
          -> cypher_guard
          -> devuelve_respuesta
          -> redacta_respuesta
  -> guarda_memoria_corta
  -> END
```

La contextualización automática (`contextualiza_pregunta` y
`contextualized_prompt_injection`) está desactivada temporalmente. Cada turno continúa con
la pregunta original después de la primera validación.

El orquestador GPT-OSS 120B clasifica la consulta sin responderla. Saludos y conversación pasan
al analista GPT-OSS 20B; las preguntas con hechos del grafo cargan el schema vivo y pasan a Luna
Max para generar Cypher. Las filas verificadas vuelven al analista 20B para la respuesta final.
No hay planner ni catálogo de plantillas en el flujo activo.

## Contratos firmes

- Neo4j se consulta únicamente con routing `READ`.
- El schema vivo es la fuente de verdad para labels, propiedades y relaciones.
- La generación Cypher admite como máximo dos intentos y cada salida pasa validación de schema,
  resolución de entidades y guarda final.
- Toda consulta lleva un límite entre 1 y 100.
- Las filas verificadas se redactan con el analista 20B, sin detalles de Cypher. Los IDs solo
  se entregan al modelo cuando la pregunta los solicita explícitamente.
- La memoria corta conserva hasta cuatro turnos por 30 minutos, con límites globales de capacidad.
- La caché de consultas pertenece al dashboard tipado; el chat no usa caché de resultados.

## Verificación actual

Desde `backend/`:

```powershell
python -m pytest -q
python -m ruff check .
python -m mypy agente api
python -m compileall -q agente api scripts
```

Desde `frontend/`:

```powershell
npm run check
```

La aceptación externa se verifica por separado con una pregunta real contra Neo4j y OpenAI. Las
auditorías reutilizables viven en `backend/scripts/auditoria_cypher_estructurada.py`.

## Pendientes de producto

- Autenticación y rate limiting antes de exposición pública.
- CI/CD, despliegue reproducible y observabilidad operativa.
- Evaluación semántica continua con preguntas reales y expectativas sobre valores, no solo forma.

## Decisiones vigentes

- Solo Neo4j y OpenAI; no incorporar Supabase ni pgvector en este agente.
- No aceptar Cypher arbitrario en endpoints públicos.
- No reintroducir planner, plantillas o código histórico sin una necesidad y pruebas nuevas.
- El contenido histórico permanece en `sesiones/agente-langgraph.md`, pero no describe el runtime
  actual.
