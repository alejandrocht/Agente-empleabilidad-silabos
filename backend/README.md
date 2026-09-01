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

## Normalizadores de Empleabilidad y Sílabos

El primer vertical del normalizador recibe el XLSX sin exigir años fijos. Identifica las hojas
por los roles `Convenios`, `Informes` y `Publicaciones`, valida sus columnas mínimas, calcula el
hash de la fuente y devuelve un ID de ejecución. La validación ocurre en segundo plano y no
bloquea el chat ni el dashboard.

```text
POST /normalizador/empleabilidad
GET  /normalizador/ejecuciones/{id_ejecucion}
GET  /normalizador/ejecuciones/{id_ejecucion}/errores
```

La respuesta distingue `limpiado`, `limpiado_con_advertencias`, `rechazado` y `error`. Cuando la
entrada es válida, genera tres JSONL de staging bajo `limpios/`, con valores estructuralmente
limpios, IDs reproducibles y referencia a la hoja/fila de origen. Luego aplica el catálogo CHH
versionado, conserva la evidencia y separa las propuestas de herramienta que requieren revisión.
Una ejecución pasa a `normalizado` solo si las relaciones candidatas cumplen las puertas de
publicación; en caso contrario queda en `no_publicado` con hallazgos y cuarentena consultables.

El vertical curricular recibe una fuente declarando carrera y periodo. Acepta un DOCX o PDF
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

El corte curricular valida el paquete, extrae metadatos, sumilla, logro general, logros específicos
y programa analítico. El JSONL de limpieza es staging interno y no se ofrece como salida de negocio.
Cada ejecución conserva exactamente cuatro CSV curriculares como paquete candidato:

```text
salidas/catalogo_competencias.csv
salidas/catalogo_habilidades.csv
salidas/catalogo_herramientas.csv
salidas/cobertura_curricular.csv
```

La cobertura solo contiene `id_cob_curricular`, `id_curso`, `id_silabo`, `id_competencia`,
`id_habilidad` e `id_herramienta`. El último campo puede estar vacío; los demás identifican la
relación atómica y conectan cada resultado con el curso y el sílabo de origen. La proveniencia
detallada se conserva en `salidas/reportes/{competencias,habilidades,herramientas}_fuente.jsonl` y
en `cobertura_curricular_fuente.jsonl`; las propuestas no catalogadas quedan en
`pendientes_curriculares.jsonl` con un `id_pendiente` estable, evidencia y estado explícito.

Cuando el LLM propone una competencia, habilidad o herramienta que no coincide con el catálogo,
la interfaz muestra un checkpoint al finalizar la ejecución. El ejecutor envía un lote con
`{"id_pendiente":"...","decision":"ADD"}` o `KEEP_PENDING`. `ADD` promueve el concepto solo
al perfil de carrera/periodo, genera provenance y recalcula el release gate; `KEEP_PENDING` conserva
la evidencia fuera de los CSV canónicos. Ambas decisiones quedan en
`reportes/decisiones_curriculares.jsonl` y una repetición exacta es idempotente.

El reporte `release_gate.json` es la decisión de publicación para Neo4j. Los pendientes preservados
son válidos en un borrador, pero una salida solo puede importarse cuando el gate indica
`ALLOW_IMPORT`; provenance incompleta, relaciones canónicas no verificadas o errores estructurales
mantienen `BLOCK_IMPORT`. Así la revisión humana se concentra en ambigüedades y evolución del perfil,
no en cada logro claro.

Cada ejecución curricular está aislada por la pareja declarada `carrera` + `periodo`: esa pareja se
normaliza, se conserva en el registro y forma parte de los IDs de curso y sílabo. No se aplica un
mapa global fijo de `L1`, `E1` o `G1`; esos códigos se validan dentro del sílabo que los declara.
Cuando un logro referencia un código ausente o ambiguo, la descripción textual del logro conserva la
relación y el catálogo CHH solo ayuda a canonicalizarla. La inconsistencia se reporta como advertencia;
solo una falta de evidencia utilizable genera cuarentena.

El alcance de competencias es curricular, no global: si existe
`catalogos/carreras/{CARRERA}/{PERIODO}/`, se usa ese catálogo; si aún no existe, se construye un perfil
provisional con las competencias declaradas por los sílabos de la ejecución. El catálogo global conserva
el vocabulario compartido de habilidades y herramientas, pero no puede inventar una competencia de otra
carrera. Las referencias no declaradas (por ejemplo, `EE`) se conservan como evidencia de fuente y se
reportan para revisión. DOCX y PDF admiten códigos `E/G` numéricos y alfabéticos de forma acotada.

### Analista curricular LLM por carrera

En producción la ejecución curricular debe activar el analista semántico y su inspector. Para ello:

```dotenv
NORMALIZADOR_CURRICULAR_LLM=true
NORMALIZADOR_CURRICULAR_INSPECTOR=true
OPENAI_MODEL_CURRICULAR=gpt-5.6-luna
# Opcional: si no se define, el inspector curricular usa el mismo modelo.
OPENAI_MODEL_INSPECTOR_CURRICULAR=gpt-5.6-luna
# Opcional: Terra solo para residuales semánticos; por defecto permanece desactivado.
NORMALIZADOR_CURRICULAR_ESCALAR_RESIDUALES=false
OPENAI_MODEL_CURRICULAR_RESIDUAL=gpt-5.6-terra
OPENAI_MODEL_INSPECTOR_CURRICULAR_RESIDUAL=gpt-5.6-terra
LLM_TIMEOUT_SECONDS=120
LLM_MAX_RETRIES=2
```

La primera pasada usa Luna para el analista y el inspector (`OPENAI_MODEL_CURRICULAR` y
`OPENAI_MODEL_INSPECTOR_CURRICULAR`). El escalamiento residual está desactivado por defecto con
`NORMALIZADOR_CURRICULAR_ESCALAR_RESIDUALES=false`; al activarlo, solo los residuales semánticos
se envían a Terra mediante `OPENAI_MODEL_CURRICULAR_RESIDUAL` y
`OPENAI_MODEL_INSPECTOR_CURRICULAR_RESIDUAL`. Se escalan únicamente decisiones con
`LLM_SOLICITA_REVISION` o `CONFIANZA_BAJA`. No se escalan fallos mecánicos de evidencia,
herramientas o formato: Python los conserva como revisión determinista.

El analista recibe lotes compactos de logros, sumilla, contenido y perfil de la carrera. Devuelve
competencia, habilidad, herramientas y evidencia en JSON estructurado; Python genera los IDs,
normaliza nominalizaciones cerradas y valida la evidencia estructurada del programa analítico.
También rechaza habilidades genéricas, herramientas no detectadas, evidencia ausente o baja
confianza. El inspector puede aprobar, revisar o rechazar cada decisión. Si el proveedor falla,
se conserva el resultado determinista y se registra `ANALISTA_LLM_NO_DISPONIBLE`.

La auditoría se guarda fuera de los CSV en `salidas/reportes/decisiones_llm.jsonl` y
`salidas/reportes/analisis_llm.json`. Los reportes incluyen los modelos y las decisiones escaladas
para mantener la trazabilidad. Python no modifica los CSV: los cuatro archivos mantienen exactamente
sus columnas actuales.

### Embeddings curriculares por carrera (opt-in)

La recuperación semántica es opcional y solo sugiere candidatos CHH al LLM por cada logro. No mezcla
el corpus laboral, se limita al catálogo de la misma `carrera` + `periodo`, y nunca se considera
evidencia: Python sigue verificando las citas contra el sílabo literal antes de aprobar una decisión.

```dotenv
# Requiere OPENAI_API_KEY y un catálogo curricular revisado para la carrera/periodo.
NORMALIZADOR_CURRICULAR_EMBEDDINGS=true
NORMALIZADOR_CURRICULAR_EMBEDDING_CARRERAS=MARKETING@2026-1,INGENIERIA@2026-1
NORMALIZADOR_EMBEDDING_MODEL=text-embedding-3-small
# Se aceptan únicamente similitudes estrictamente mayores al umbral.
# El valor seguro por defecto 0 excluye similitudes cero y negativas.
NORMALIZADOR_CURRICULAR_EMBEDDING_MIN_SIMILARITY=0
```

Ambos controles (`NORMALIZADOR_CURRICULAR_EMBEDDINGS` y la allowlist
`NORMALIZADOR_CURRICULAR_EMBEDDING_CARRERAS`) deben habilitar exactamente la pareja carrera + periodo
enviada; las entradas antiguas que solo contienen una carrera fallan cerrado. Sin credenciales,
catálogo específico, proveedor/vector válido o candidatos por encima del umbral, el sistema usa el
fallback lexical y registra solo un `reason_code` estable: `embedding_retriever_absent`,
`embedding_catalog_empty`, `embedding_provider_or_vector_invalid` o
`embedding_candidates_below_threshold`. La auditoría no persiste mensajes de excepción, rutas ni
secretos.

Las herramientas no se buscan en el texto completo: únicamente se aceptan cuando aparecen en una sección
estructurada de recursos, software, herramientas digitales o programa analítico. El programa analítico es
una fuente estructurada válida después de excluir bibliografía, URLs y recursos docentes genéricos; esas
fuentes siguen sin ser herramientas publicables. Esto también impide publicar coincidencias de apellidos o
términos financieros. Cada evidencia incluye sección, texto fuente y coincidencia en
`herramientas_fuente.jsonl`; se reconocen alias explícitos como `MS Excel` → `Microsoft Excel`.

### Contrato evidence-first y esquemas CSV

El flujo curricular es determinista y respeta la evidencia en este orden:

1. registra todas las competencias declaradas por cada sílabo;
2. resuelve el logro contra esas declaraciones dentro del mismo sílabo; si el código es
   ambiguo o no está declarado, conserva el código como referencia de fuente y solo usa la
   descripción para una relación textual revisable;
3. intenta canonicalizar la habilidad contra el catálogo de habilidades, primero por nombre exacto
   y luego con coincidencia lexical fuerte; si no hay evidencia suficiente, no inventa una fila
   pública y la conserva como pendiente con propuesta/evidencia;
4. busca herramientas explícitas solo en secciones curriculares estructuradas y las relaciona con la
   competencia principal de la habilidad, evitando productos cartesianos; y
5. ejecuta un juez determinista que rechaza esquemas inválidos, IDs duplicados, relaciones huérfanas
   y competencias placeholder.

Los cuatro CSV del paquete candidato conservan exactamente las columnas de los catálogos existentes; no se
agregan columnas ni archivos CSV alternativos:

```text
catalogo_competencias.csv:
id_competencia,nombre_competencia,descripcion_breve_competencia,tipo_competencia
catalogo_habilidades.csv:
id_habilidad,nombre_habilidad,descripcion_breve
catalogo_herramientas.csv:
id_herramienta,nombre_herramienta,descripcion_breve_herramienta
cobertura_curricular.csv:
id_cob_curricular,id_curso,id_silabo,id_competencia,id_habilidad,id_herramienta
```

La evidencia que no puede expresarse en ese contrato se guarda como JSONL de auditoría en
`salidas/reportes/`: `competencias_fuente.jsonl`, `habilidades_fuente.jsonl`,
`herramientas_fuente.jsonl`, `cobertura_curricular_fuente.jsonl` y
`cobertura_curricular_canonica.jsonl`. Las resoluciones incluyen método, puntaje y segundo puntaje para
que coincidencias ambiguas se mantengan en revisión. Esos reportes no alteran los esquemas CSV y permiten
revisar qué declaró cada sílabo sin publicar placeholders.

### Perfil bootstrap por carrera

Después de revisar una ejecución, se puede generar un perfil inicial sin alterar los esquemas CSV:

```bash
uv run --locked python -m scripts.generar_perfil_carrera \
  --ejecucion .normalizador/NOR_xxx \
  --catalogos "/ruta/Normalizacion CIAR/catalogos" \
  --carrera Marketing --periodo 2026-1
```

El resultado queda en `catalogos/carreras/MARKETING/2026-1/` con los tres catálogos y cobertura opcional.
`perfil.json` conserva `BORRADOR_CON_PENDIENTES` mientras exista cola abierta (o `BORRADOR` si está vacía);
las habilidades, competencias y herramientas no canónicas quedan en
`reportes/pendientes_curriculares.jsonl` y `habilidades_pendientes.jsonl`, no en columnas nuevas ni como
conceptos inventados. Mientras
un perfil está en bootstrap, especializa el espacio de **competencias**; las habilidades y herramientas aún se
contrastan contra el catálogo global para que un perfil incompleto no elimine candidatos y fuerce falsos positivos.

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
