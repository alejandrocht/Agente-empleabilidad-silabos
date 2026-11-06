# Local Qwen HITL smoke test

Status: in progress
Repository: Agente-empleabilidad-silabos

## Goal
Download user-selected Ollama `qwen3:8b`, run the existing backend locally with the curricular analyst pointed at it, and smoke-test health and actual model/schema output without mutating existing normalizer runs or uploading real syllabi.

## Decisions and constraints
- User selected `qwen3:8b` (~5.2 GB) rather than nonexistent `qwen3.8:8b` or resource-heavy `qwen3.8:27b`.
- Existing Ollama binary is present; 24 GB RAM, ~67 GiB available disk; Next dev listens on 127.0.0.1:3000; 8001 currently free at inspection.
- Use temporary process environment overrides, do not alter tracked config or `.env`, and do not run root `start_services.sh` because it kills existing listeners.
- Preserve all unrelated dirty files. No commit, push, real credentials, or destructive process cleanup. Run only synthetic data for a live model smoke.
- Exact backend route: `cd backend && .venv/bin/python -m uvicorn api.servidor:app --host 127.0.0.1 --port 8001`, with `NORMALIZADOR_CURRICULAR_LLM_PROVIDER=ollama`, `NORMALIZADOR_CURRICULAR_OLLAMA_BASE_URL=http://127.0.0.1:11434/v1`, `NORMALIZADOR_CURRICULAR_OLLAMA_MODEL=qwen3:8b`, and `NORMALIZADOR_CURRICULAR_LLM=true` when required by the code.
- The Engram mirror `odd/local-qwen-hitl-smoke/tasks` is pending if Engram remains unavailable.

## Tasks
- [x] T1 Download `qwen3:8b` and verify installed tag, live Ollama API and a minimal schema response. Ollama 0.32.14, model ID 500a1f067a9f; JSON-schema HTTP 200, parsed exact fields in 2.11 s. This does not prove full curricular schema/quality.
- [x] T2 Launch backend bound to 127.0.0.1:8001 with Ollama overrides. PID 59746 remains active; `/health` HTTP 200; Ollama API HTTP 200. Existing frontend previously observed on 3000 exited independently (cause unknown; no evidence backend launch caused it), so start it separately before UI check.
- [ ] T4 Restore stable frontend listener on 127.0.0.1:3000. First Next dev PID 62633 served the UI (`/normalizador` 200) and two browser switch clicks each posted `/api/normalizador/eventos/hitl` 204; it subsequently exited without a recorded error. A direct Next binary retry PID 66732 also exited before the 10-second check; frontend stability remains blocked, not done.
- [x] T3 Live Qwen + synthetic syllabus through isolated backend 8002, `NORMALIZADOR_DATA_DIR=/tmp/ciar-qwen-e2e.ew5S9G/data`. Auto run `NOR_72a38a07f4b84659`: manifest `qwen3:8b`, hitl=0, one model proposal, automatic ADD, ALLOW_IMPORT and 6 CSVs with HAB_TEC_0090. Manual run `NOR_4fd48c14d9ac4e49`: manifest hitl=1, one pending proposal, BLOCK_IMPORT/PENDING_TECHNICAL_APPROVAL, 0 skill rows before decision; base CSV files existed but gated. Manual API ADD returned HTTP 200, ALLOW_IMPORT, 1 skill row HAB_TEC_0090. All data synthetic and isolated from existing runs.

- [x] T5 Independently validated both synthetic final CSV packages: each has rows curso=1, silabo=1, competencias=1, habilidades=1, logros=2, cobertura=3. Headers match `ARCHIVOS_CATALOGO`, primary IDs are nonempty/unique, nonempty coverage references resolve, both manifests show ALLOW_IMPORT and qwen3:8b. Six CSVs are byte-identical across automatic and post-manual-ADD runs. This establishes structural compatibility, not semantic correctness for real syllabi.
- [x] T6 Packaged both sets (12 CSVs) into `/Users/alejandromcht/Desktop/paquetes-hitl-qwen3-8b.zip` (4,991 bytes), with LEEME.txt and SHA256SUMS.txt. Archive CRC and all 12 checksums passed; same-name auto and manual CSVs are byte-identical. ZIP SHA-256: `7de0d70ae8721490fb995e6c7da9fbfaa2a0cfa75a5ad92fa2b315f46ffa3ba0`.

## Next step
Deliver the archive path and concise structural verdict; explicitly flag one-syllabus synthetic limitations and unresolved frontend stability (Next dev exits). No model download or backend restart needed for CSV review. Current Ollama and backend 8001 are healthy; isolate-backend 8002 may be stopped after tests without deleting the temp artifacts. Note: the first backend nohup one-liner started Uvicorn but failed to write PID file due to `&` precedence; incident diagnosed read-only. Avoid `start_services.sh`.
