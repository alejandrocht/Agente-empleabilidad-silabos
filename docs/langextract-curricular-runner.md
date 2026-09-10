# LangExtract Curricular Runner

The runner is an explicit diagnostic tool. It does not alter the normalizer, catalog, JSONL, CSV, approval flow, API, or release gate.

It accepts explicit DOCX paths and emits one JSON object with `documentos`. Each document includes the source path and SHA-256, detected structure, accepted `paquetes`, `pendientes`, `errores`, and `resumen`. The summary reports generated proposals, accepted packages, pending counts by reason, and errors. Accepted packages have Python-verified literal citations and character intervals. Invalid evidence and extraction failures become pending rows; no output is automatically approved.

The default is one LangExtract call per DOCX. `--chunk-chars` explicitly allows chunking. Use it only when needed; the JSON reports each fragment's accepted packages, pending rows, and errors, plus the aggregate result per input document.

The model receives the complete weekly program as primary evidence, including its titles, descriptions, practice, workshops, and project text. `Programa analítico` tables are reconstructed row-by-row: topic and content become primary evidence, while the week number is structural metadata and never reasoning text. Declared competencies, learning outcomes, and sumilla are tagged as complementary context. Bibliography, methodology, administration, and table numbering are excluded from tool-teaching evidence. Paths, hashes, and reporting metadata never enter the model payload.

A proposed tool is accepted only when it has an explicit name, a verified literal citation from `programa_semanal`, an admitted ontology type, and a use citation overlapping the package's primary skill evidence. Catalog resolution scans tool mentions independently, then links a tool only when the extracted package explicitly names that tool and its literal use overlaps that package's skill citation. Other mentions are emitted as `herramientas_sin_vinculo`. Educational activities, methods, products or artifacts, diagrams, UML notation, generic categories, and generic ERP labels stay pending. A rejected tool never removes an otherwise supported skill package.

Every rejected primary citation has bounded `diagnostico_cita` fields: `texto_modelo`, `intervalo`, `fragmento_fuente`, and `razon_rechazo`. This makes per-course failures traceable without relaxing literal evidence.

With the already synchronized environment and the key supplied through the environment, run the ten selected DOCX files in one pass:

```bash
cd backend
OPENAI_API_KEY="$OPENAI_API_KEY" uv run --no-sync python -m agente.normalizador.silabos.langextract_runner \
  "$HOME/Desktop/Silabos_train"/*.docx
```

The `ciar-openai/<OpenAI model>` provider builds a stable CIAR system instruction independently. The LangExtract-generated request body is transported unchanged as the OpenAI `user` message; it is never split on `Q:` or `A:`, so document text cannot enter the system message. The default request bounds are 120 seconds and zero retries. A timeout becomes `LLM_REQUEST_TIMEOUT`, records duration, and the next document continues.

## Optional Catalog And Recovery

Catalog use is explicit and has no cross-career fallback. The selected directory must contain the three standard CSV files and `catalogo_metadata.json` with non-empty provenance, career, period, and version. CSV files are decoded with `utf-8-sig`.

```json
{
  "career": "Ingeniería de Sistemas",
  "period": "2026-2",
  "version": "v1",
  "provenance": "approved catalog export 2026-2",
  "aliases": {"herramienta": {"Node": "Node.js"}}
}
```

The runner loads and validates this catalog once before its first LLM request. An invalid selection returns `catalogo_preflight.estado=BLOQUEADO`; it invokes no extractor and has no raw proposals. A later document-metadata mismatch preserves `paquetes_crudos` and leaves canonical IDs unset.

Use a writable directory outside the repository for durable records. `--stream` writes one safe NDJSON document record immediately after each document and a final summary. `--resume` skips valid saved records and retries only missing or failed records. `--resolve-only` applies a valid catalog to those saved raw results without any LLM call.

```bash
# Validate a selected catalog without OPENAI_API_KEY or document extraction.
uv run --no-sync python -m agente.normalizador.silabos.langextract_runner \
  --preflight-only --catalog-dir /external/catalogs/systems-2026-2 \
  --career "Ingeniería de Sistemas" --period 2026-2 --catalog-version v1

# Generic streamed extraction without a catalog. No canonical IDs are created.
uv run --no-sync python -m agente.normalizador.silabos.langextract_runner \
  --stream --results-dir /external/langextract-results \
  /external/syllabi/*.docx

# Selected catalog extraction, then resolve an existing saved run without an LLM call.
uv run --no-sync python -m agente.normalizador.silabos.langextract_runner \
  --stream --results-dir /external/langextract-results --resume \
  --catalog-dir /external/catalogs/systems-2026-2 \
  --career "Ingeniería de Sistemas" --period 2026-2 --catalog-version v1 \
  /external/syllabi/*.docx
uv run --no-sync python -m agente.normalizador.silabos.langextract_runner \
  --resolve-only --results-dir /external/langextract-results \
  --catalog-dir /external/catalogs/systems-2026-2 \
  --career "Ingeniería de Sistemas" --period 2026-2 --catalog-version v1
```

## Reference-Only Candidate Suggestions

`--reference-catalog-dir` is advisory-only. It accepts a directory with the three
standard CSV files, decoded as `utf-8-sig`, but does not require
`catalogo_metadata.json`. It never emits a canonical ID, selects a target catalog,
resolves coverage, or approves a C-H-H relation. The output labels its scope as
`catalogo_referencia.modo=reference_only` and keeps each raw proposal unchanged.

For every raw competence, skill, and tool, `paquetes[].referencia` contains a
`candidatos_humanos` list. Every candidate has only `nombre`, `descripcion`, `score`,
`catalog_source`, and `catalog_type`; a human must choose any later catalog identity.
Catalog names create case, accent, punctuation, and compact aliases mechanically.
Optional human-maintained aliases can be added in `catalogo_aliases.json`:

```json
{
  "herramienta": {"nombre alternativo": "Nombre del catálogo"}
}
```

Candidates use `rapidfuzz.process.extract` with `fuzz.WRatio`,
`utils.default_process`, a top-three limit, and a `75` score cutoff. Suggestions do
not cross careers: the supplied reference directory remains visible in the output and
the future target catalog selection is an explicit human action.

It cannot be combined with `--catalog-dir`, `--career`, `--period`, or
`--catalog-version`. This benchmark command keeps the durable records outside the
repository and runs all DOCX matched by the injected path:

```bash
cd backend
RESULTS_DIR="$(mktemp -d /tmp/ciar-langextract-luna-max-XXXXXX)"
OPENAI_API_KEY="$OPENAI_API_KEY" uv run --no-sync python -m agente.normalizador.silabos.langextract_runner \
  --profile benchmark --model gpt-5.6-luna --reasoning-effort max \
  --reference-catalog-dir "<user reference csv dir>" \
  --stream --results-dir "$RESULTS_DIR" \
  "$HOME/Desktop/Silabos_train"/*.docx
```
