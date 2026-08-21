# CIAR Agent Backend

The active backend lives in `backend/agente`. It uses LangGraph, OpenAI, and Neo4j to
answer Spanish questions about the CIAR academic and employment graph. Domain queries
are read-only and pass through the current Cypher guard and Neo4j `READ` gateway.

## Install

From the repository root:

```powershell
cd backend
python -m pip install -e ".[dev]"
Copy-Item .env.example .env  # only when .env does not exist
```

Fill `.env` with OpenAI credentials and Neo4j credentials. Use a read-only Neo4j
principal for domain queries.

## Run

The console uses the async `responder` entrypoint:

```powershell
cd backend
python scripts/consola.py
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
GET  /normalizador/ejecuciones/{id_ejecucion}
GET  /normalizador/ejecuciones/{id_ejecucion}/errores
GET  /normalizador/ejecuciones/{id_ejecucion}/cuarentena
```

El corte curricular valida el paquete, extrae metadatos, sumilla, logro general, logros específicos
y programa analítico. El JSONL de limpieza es staging interno y no se ofrece como salida de negocio.
Cuando pasan las puertas curriculares, se publican exactamente cuatro CSV:

```text
salidas/catalogo_competencias.csv
salidas/catalogo_habilidades.csv
salidas/catalogo_herramientas.csv
salidas/cobertura_curricular.csv
```

La cobertura solo contiene `id_cob_curricular`, `id_curso`, `id_silabo`, `id_competencia`,
`id_habilidad` e `id_herramienta`. El último campo puede estar vacío; los demás identifican la
relación atómica y conectan cada resultado con el curso y el sílabo de origen. Si alguna puerta falla,
los CSV no se publican y la ejecución queda en `no_publicado` con hallazgos y cuarentena consultables.

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
   pública y la conserva en el reporte de fuente;
4. busca herramientas explícitas solo en secciones curriculares estructuradas y las relaciona con la
   competencia principal de la habilidad, evitando productos cartesianos; y
5. ejecuta un juez determinista que rechaza esquemas inválidos, IDs duplicados, relaciones huérfanas
   y competencias placeholder.

Los cuatro CSV publicados conservan exactamente las columnas de los catálogos existentes; no se
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
python -m scripts.generar_perfil_carrera \
  --ejecucion .normalizador/NOR_xxx \
  --catalogos "/ruta/Normalizacion CIAR/catalogos" \
  --carrera Marketing --periodo 2026-1
```

El resultado queda en `catalogos/carreras/MARKETING/2026-1/` con los tres catálogos y cobertura opcional.
`perfil.json` lo identifica explícitamente como `REQUIERE_REVISION_HUMANA`; las habilidades no canónicas
quedan en `reportes/habilidades_pendientes.jsonl`, no en columnas nuevas ni como conceptos inventados. Mientras
un perfil está en bootstrap, especializa el espacio de **competencias**; las habilidades y herramientas aún se
contrastan contra el catálogo global para que un perfil incompleto no elimine candidatos y fuerce falsos positivos.

## Logs
The current FastAPI application is `api.servidor:app`:

```powershell
cd backend
python -m uvicorn api.servidor:app --reload --port 8001
```

It exposes `/health`, `/chat`, `/chat/stream`, `/preguntar`, and the typed read-only
dashboard endpoints under `/dashboard/`. No endpoint accepts arbitrary Cypher.

## Active architecture

- `agente/grafo/constructor.py` contains the graph factory and the no-argument
  `langgraph_entrypoint` referenced by `langgraph.json`.
- `agente/utils/tooler.py` contains exactly 20 immutable, parameter-validated Cypher
  templates. A deterministic exact match skips planning; uncertain questions use the
  planner/dynamic route.
- `agente/cache/consultas.py` provides a thread-safe process-local LRU cache of
  successful normalized query rows. It uses a 600-second TTL and 256-entry limit by
  default, configured by `QUERY_RESULT_CACHE_TTL_SECONDS` and
  `QUERY_RESULT_CACHE_MAX_ENTRIES`.
- The graph is stateless and compiles without a LangGraph checkpointer. `thread_id` is
  retained only as an HTTP correlation identifier; requests do not share state.
- `agente/utils/response_inspector.py` performs deterministic checks on every final
  response. Invalid output is replaced by a safe fallback; no `INSPECTOR_LLM` setting
  is active.
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
python -m scripts.ingest_documents .\imports\syllabus.md .\imports\jobs.json
# Example: cap this dry run to one source while keeping the default batch size.
python -m scripts.ingest_documents --max-documents 1 .\imports\syllabus.md
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
the planner, entity resolution, or the domain query gateway.

See `.env.example` for all current schema-cache, query-cache, logging, and role-specific
OpenAI settings.

## Verification

From `backend/`:

```powershell
python -m pytest -q
python -m ruff check .
python -m mypy agente
python -m compileall -q agente api scripts
python -c "from agente.grafo.constructor import langgraph_entrypoint; langgraph_entrypoint()"
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
