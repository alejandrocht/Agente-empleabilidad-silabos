# CIAR Agent Backend

The active backend lives in `backend/agente`. It uses LangGraph, OpenAI, and Neo4j to
answer Spanish questions about the CIAR academic and employment graph. Domain queries
are read-only and pass through the current Cypher guard and Neo4j `READ` gateway.

## Install

From the repository root:

```powershell
cd backend
uv sync --locked --extra dev
Copy-Item .env.example .env  # only when .env does not exist
```

Use the project environment for every backend command. If invoking Python directly,
use `backend/.venv/bin/python` from the repository root; do not use a bare `python`.

Fill `.env` with OpenAI credentials and Neo4j credentials. Use a read-only Neo4j
principal for domain queries.

## Run

The console uses the async `responder` entrypoint:

```powershell
cd backend
uv run --locked python scripts/consola.py
```

Exit with `/salir`.

## Normalizador Curricular/Técnico de Sílabos

El normalizador recibe una fuente declarando carrera y periodo. Acepta un DOCX o PDF
individual, o un ZIP con varios archivos seguros:

```text
POST /normalizador/silabos
     multipart: archivo, carrera, periodo
POST /normalizador/silabos/cactus
     JSON: carrera, periodo, usuario, contrasena
GET  /normalizador/ejecuciones/{id_ejecucion}
GET  /normalizador/ejecuciones/{id_ejecucion}/errores
GET  /normalizador/ejecuciones/{id_ejecucion}/cuarentena
GET  /normalizador/ejecuciones/{id_ejecucion}/pendientes
POST /normalizador/ejecuciones/{id_ejecucion}/pendientes/decidir
GET  /normalizador/ejecuciones/{id_ejecucion}/release-gate
```

`/normalizador/silabos/cactus` ejecuta el adapter de extracción sobre Cactus/ULima y entrega
los archivos PDF/DOCX descargados al mismo pipeline de validación, limpieza, revisión y release
gate. El usuario selecciona carrera y periodo desde la interfaz y proporciona sus credenciales
solo para esa ejecución: no se incluyen en el manifest, reportes ni parámetros persistidos. La
sesión del navegador y sus cookies viven en el directorio temporal de la ejecución y se purgan al
finalizar. Si Cactus entrega una cobertura parcial, los archivos se conservan como evidencia,
pero `EXTRACTION_COVERAGE_INCOMPLETE` bloquea la publicación.

Cada ejecución usa `hitl=1` por defecto y puede cambiarse a `hitl=0` solo para esa corrida; en 0 las propuestas técnicas válidas se registran automáticamente como `ADD` y la decisión queda en el diario de auditoría. La publicación y la descarga/importación siguen requiriendo que todos los controles del release gate permitan `ALLOW_IMPORT`.

El extractor requiere Playwright y un navegador Chromium instalado en el entorno del backend:

```powershell
cd backend
uv run --locked python -m playwright install chromium
```

Durante desarrollo puede configurarse el comportamiento del navegador y la concurrencia:

```dotenv
NORMALIZADOR_CACTUS_HEADLESS=false
NORMALIZADOR_CACTUS_DOWNLOAD_WORKERS=3
```

El corte curricular valida el paquete y extrae cada sílabo una sola vez, incluyendo metadatos,
sumilla, logros y programa analítico. El JSONL de limpieza es staging interno y no se ofrece como salida
de negocio. La ejecución técnica conserva exactamente seis CSV:

```text
salidas/curso.csv
salidas/silabo.csv
salidas/catalogo_competencias.csv
salidas/catalogo_habilidades.csv
salidas/catalogo_logros.csv
salidas/cobertura_curricular.csv
```

El analista técnico recibe carrera, nombre del curso, resultados de aprendizaje, las filas extraídas de
`programa_analitico_detalle` (`semana`, `tema`, `contenido`) y candidatos del catálogo técnico. No recibe
IDs, periodo, sumilla, competencias declaradas, herramientas ni relaciones del grafo.

La cobertura conecta curso y sílabo con un logro y exactamente una competencia declarada o una habilidad técnica. Las habilidades aprobadas usan el catálogo público `catalogo_habilidades.csv`; las referencias oficiales `COMP_TEC_####` se publican como `HAB_TEC_####` y las propuestas técnicas aprobadas sin referencia de catálogo también reciben un ID `HAB_TEC_####`.

Los IDs `HAB_TEC_####` son globales: la identidad de una habilidad es el par nombre normalizado + descripción normalizada, independiente de la carrera. Si el catálogo oficial repite `COMP_TEC_####` en varias carreras para el mismo contenido, todas las filas conservan un único `HAB_TEC_####`. `id_carrera` permanece en el CSV por contrato y como metadato de procedencia, pero no forma parte de la identidad de `Habilidad`. El contexto de carrera se obtiene por `Curso` → `CoberturaCurricular` → `Habilidad`; no se crean relaciones directas `Carrera`–`Habilidad`.

El registro persistente vive en `catalogos/habilidades.sqlite3` bajo la raíz de ejecución compartida, junto a los directorios `NOR_*`; no forma parte de los catálogos oficiales. Al inicializarlo, cada sufijo oficial `COMP_TEC_####` reserva su correspondiente `HAB_TEC_####`. Una propuesta sin referencia reutiliza el ID de la misma identidad normalizada o recibe el siguiente sufijo libre, sin colisionar con sufijos oficiales ni registrados. La resolución y la materialización son transaccionales: ante un error se revierte el registro SQLite junto con los CSV materializados, el diario de decisiones y el `manifest.json`.

La proveniencia
y las propuestas técnicas se conservan en `salidas/reportes/`, principalmente
`analisis_tecnico.json`, `propuestas_tecnicas.jsonl` y `decisiones_tecnicas.jsonl`. Cada propuesta tiene
evidencia literal de un logro y queda `PENDIENTE_APROBACION` hasta que la revisión técnica registra
`ADD`, `DISCARD` o `KEEP_PENDING`.

El reporte `release_gate.json` es la decisión de publicación para Neo4j. Una salida solo puede importarse
cuando el gate indica `ALLOW_IMPORT`; evidencia incompleta, propuestas sin decisión o referencias
huérfanas mantienen `BLOCK_IMPORT`.

Cada ejecución curricular está aislada por la pareja declarada `carrera` + `periodo`: esa pareja se
normaliza, se conserva en el registro y forma parte de los IDs de curso y sílabo. Python genera todos los
IDs y relaciones del grafo; el catálogo técnico solo aporta candidatos para el análisis. DOCX y PDF pasan
por el mismo extractor curricular y cada sílabo se analiza una sola vez.

### Analista técnico LLM

El normalizador curricular usa un único contrato técnico. La configuración siempre fija
`modo_analista=technical` y carga el mapa oficial carrera-competencia desde
`backend/catalogos/carrera_competencia_oficial.csv`. Ese CSV aporta `id_carrera`,
`nombre_carrera`, `id_habilidad` y `nombre_habilidad`; el cargador une cada fila por carrera y
nombre normalizados con `backend/catalogos/catalogo_competencias_tecnicas.xlsx`, que continúa
siendo la fuente de descripciones y compatibilidad para los formatos anteriores. La unión es
estricta: no usa fuzzy matching ni búsquedas aproximadas.

```dotenv
NORMALIZADOR_CURRICULAR_LLM=true
NORMALIZADOR_CURRICULAR_LLM_PROVIDER=ollama
NORMALIZADOR_CURRICULAR_OLLAMA_BASE_URL=http://localhost:11434/v1
NORMALIZADOR_CURRICULAR_OLLAMA_MODEL=qwen3.8:27b
NORMALIZADOR_CURRICULAR_OPENAI_MODEL=gpt-5.6-luna
NORMALIZADOR_CURRICULAR_ANALYST_REASONING_EFFORT=medium
NORMALIZADOR_CURRICULAR_LLM_TIMEOUT_SECONDS=120
NORMALIZADOR_CURRICULAR_LLM_MAX_RETRIES=2
NORMALIZADOR_CURRICULAR_LLM_BATCH_SIZE=8
NORMALIZADOR_CURRICULAR_LLM_TEMPERATURE=0
```

Ollama usa `NORMALIZADOR_CURRICULAR_OLLAMA_MODEL`; OpenAI usa
`NORMALIZADOR_CURRICULAR_OPENAI_MODEL` y requiere `OPENAI_API_KEY`. No existe una ruta curricular
`legacy`: una ejecución de sílabos usa `analista_tecnico.py`, una llamada por sílabo y el reintento
acotado del mismo analista cuando falta una propuesta válida.

El payload del LLM contiene únicamente carrera, nombre del curso, logros, candidatos técnicos y las filas
extraídas de `programa_analitico_detalle` (`semana`, `tema`, `contenido`). No se envían IDs, periodo,
sumilla, competencias declaradas, herramientas ni relaciones del grafo. Toda propuesta debe citar un
logro literalmente; Python valida la evidencia, genera IDs y deja la decisión en
`PENDIENTE_APROBACION` hasta la revisión humana `ADD`, `DISCARD` o `KEEP_PENDING`.

La auditoría técnica se conserva en `salidas/reportes/` (`analisis_tecnico.json`,
`propuestas_tecnicas.jsonl`, `decisiones_tecnicas.jsonl` y `release_gate.json`). El gate solo permite
importar cuando indica `ALLOW_IMPORT`; propuestas pendientes, evidencia incompleta o referencias
huérfanas mantienen `BLOCK_IMPORT`.

### Contrato técnico y esquemas CSV

El paquete candidato técnico tiene exactamente estos seis archivos:

```text
curso.csv:
id_curso,nombre_curso,coordinador,creditos,nivel,tipo_curso,naturaleza,codigo_curso,id_carrera
silabo.csv:
id_silabo,codigo_silabo,sumilla,id_curso,periodo_academico
catalogo_competencias.csv:
id_competencia,nombre_competencia,descripcion_breve,tipo_competencia,codigo_competencia
catalogo_habilidades.csv:
id_habilidad,id_carrera,nombre_habilidad,desc_breve
catalogo_logros.csv:
id_logro,logro
cobertura_curricular.csv:
id_cobertura_curricular,id_curso,id_silabo,id_competencia,id_habilidad,id_logro
```

La proveniencia y las decisiones no amplían el contrato CSV: son reportes auditables fuera del paquete
canónico.

## Logs

The current FastAPI application is `api.servidor:app`:

```powershell
cd backend
uv run --locked python -m uvicorn api.servidor:app --reload --port 8001
```

It exposes `/health`, `/chat`, `/chat/stream`, `/preguntar`, and the typed read-only
dashboard endpoints under `/dashboard/`. No endpoint accepts arbitrary Cypher.

For a local graph diagnosis, set `CIAR_LOG_SCOPE=nodes` and
`CIAR_LOG_FORMAT=human`. The output is one `START/END` block with numbered nodes;
each node shows only `Enviados` and `Recibidos`. Set `CIAR_NODE_LOG_VALUES=1` only
during a local diagnosis to include bounded previews of the values; credentials and
other sensitive fields remain redacted. Keep `CIAR_LOG_FORMAT=json` for collectors.

## Active architecture

- `agente/grafo/constructor.py` contains the graph factory and the no-argument
  `langgraph_entrypoint` referenced by `langgraph.json`.
- `agente/nodos/construye_cypher.py` generates one schema-proven query and retries a rejected
  model output at most once.
- `agente/nodos/orquestador.py` uses the configured orchestration model to choose only between
  the direct and guarded graph routes; it never writes the user-facing answer.
- `agente/nodos/construye_cypher.py` uses the configured generator for schema-grounded Cypher.
- `agente/nodos/redacta_respuesta.py` uses the configured analyst to explain verified rows,
  omitting IDs unless explicitly requested. The same analyst model handles direct replies.
  The example and current local configuration map these roles to GPT-OSS 120B, Luna Max, and
  GPT-OSS 20B.
- `agente/cache/consultas.py` provides the bounded process-local LRU cache used by dashboard
  services. The chat graph does not use a result cache.
- The graph compiles without a LangGraph checkpointer. Bounded process-local conversation
  memory is reused by the scope derived from the user identity and `thread_id`; it is not
  durable across process restarts.
- `agente/utils/response_inspector.py` performs bounded safety checks on grounded analyst output.
- `agente/dashboard/consultas.py` and `agente/dashboard/servicio.py` expose the
  allow-listed dashboard data. The metadata endpoint reports supported and deferred
  datasets. Deferred datasets remain empty rather than being fabricated.

## Neo4j configuration

Domain reads prefer a complete `NEO4J_READ_*` group and otherwise use the legacy
`NEO4J_*` group. A partial higher-priority group fails closed, preserving isolation and
avoiding mixed credentials.

### Offline document graph ingestion

Source syllabi and job descriptions can be reviewed and imported offline with:

```powershell
cd backend
uv run --locked python -m scripts.ingest_documents .\imports\syllabus.md .\imports\jobs.json
# Example: cap this dry run to one source while keeping the default batch size.
uv run --locked python -m scripts.ingest_documents --max-documents 1 .\imports\syllabus.md
```

Run the CLI from `backend/` with the module form above; this is the supported and
unambiguous invocation because it preserves the package import path.

The command accepts bounded `.txt`, `.md`, `.markdown`, and explicitly shaped `.json`
documents. It runs in dry-run mode by default and prints a normalized preview without
source text, credentials, or arbitrary Cypher. JSON entries must contain only `id` or
`document_id` plus `text` or `content`.

Writing is a separate administrative operation and requires both `--write` and a
complete dedicated `NEO4J_INGEST_URI`, `NEO4J_INGEST_USER`,
`NEO4J_INGEST_PASSWORD`, and `NEO4J_INGEST_DATABASE` group. The writer never falls
back to `NEO4J_READ_*` or legacy `NEO4J_*` credentials, never deletes graph data, and
uses LangChain Neo4j's `add_graph_documents` helper with `include_source=False`.
Review and retain the dry-run preview before running the write command.

The transformer is probabilistic even with strict allow-lists. Extraction can create
incorrect entities or relationships, so previews must be reviewed and imports should
not introduce unsupported academic labels. This write path is outside the chatbot's
read-only request policy and is never called by `/chat`, `/chat/stream`, `/preguntar`,
entity resolution or the domain query gateway.

See `.env.example` for all current schema-cache, query-cache, logging, and role-specific
OpenAI settings.

## Verification

From `backend/`:

```powershell
uv run --locked python -m pytest -q
uv run --locked python -m ruff check .
uv run --locked python -m mypy agente
uv run --locked python -m compileall -q agente api scripts
uv run --locked python -c "from agente.grafo.constructor import langgraph_entrypoint; langgraph_entrypoint()"
```

The last command validates the LangGraph no-argument entrypoint and builds the graph
without opening Neo4j or calling OpenAI. Live acceptance is separate: a real Neo4j
question, deployed-schema `EXPLAIN`/execution, and external OpenAI/LangSmith access.
This offline slice does not run live services.

When frontend files are affected, run from `frontend/`:

```powershell
npm run check
npm audit --omit=dev
```

## Historical migration note

The former `backend/src/agente` package and the strategic-query runner were removed in
the active migration. Historical plans may still describe them; those sections are
context only and must not be used as current commands or import paths.
