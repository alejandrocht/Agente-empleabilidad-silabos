# SDD Project Context — Agente-empleabilidad-silabos

## Initialization Summary

This OpenSpec context was initialized for the nested Git repository `Agente-empleabilidad-silabos/` only. The active branch is `fix/high-severity-reliability` at rollback commit `c2bc753`.

## Current Session Scope

- Address the selected reliability/security work only: one critical severity finding and seven high severity findings.
- Exclude the medium severity frontend polling issue.
- Treat the curricular analyst system prompt as read-only architecture assessment material.
- Do not modify functional source code during initialization.
- Do not call a real LLM or any external paid API.
- Use fakes, contracts, and deterministic offline tests for verification.

## Project Stack

### Backend

- Python 3.11+ project in `backend/`.
- FastAPI HTTP boundary.
- LangGraph orchestration.
- LangChain Core and `langchain-openai` for LLM integration.
- Neo4j driver for read-only graph access.
- Pydantic, Playwright, document parsing, and normalizer support dependencies.

### Frontend

- Next.js 16 and React 19 project in `frontend/`.
- Vitest with jsdom for component/API tests.
- Tailwind configuration is present.

## Testing Capabilities

### Backend commands

- Install dev dependencies: `cd backend && python -m pip install -e ".[dev]"`
- Lint: `cd backend && python -m ruff check .`
- Typecheck: `cd backend && python -m mypy agente api`
- Test: `cd backend && python -m pytest -q`
- Compile: `cd backend && python -m compileall -q agente api scripts`

`backend/pyproject.toml` configures `pytest` with `testpaths = ["tests"]`, `ruff`, and strict `mypy` settings. Backend tests are already present under `backend/tests/` and `backend/tests/unit/`.

### Frontend commands

- Test: `cd frontend && npm run test`
- Build: `cd frontend && npm run build`
- Check: `cd frontend && npm run check`

`frontend/vitest.config.js` configures Vitest with `jsdom` and automatic JSX transform. Frontend tests are present under `frontend/src/**` with `.test.js` and `.test.jsx` files.

## Offline Verification Controls

- `backend/tests/conftest.py` sets `LANGSMITH_TRACING=false`.
- `backend/tests/conftest.py` sets `NORMALIZADOR_CURRICULAR_LLM=false` for deterministic normalizer tests.
- `backend/tests/conftest.py` points `NORMALIZADOR_CATALOGOS_DIR` at test fixtures.
- For this reliability/security work, any LLM, Neo4j, LangSmith, browser, or paid external boundary must be tested through fakes/contracts unless explicitly authorized later.

## Repository Conventions

- The active backend package is `backend/agente`; do not restore deleted package layouts.
- Neo4j domain access must remain read-only and guarded.
- OpenAI is the only supported LLM provider in production configuration, but live LLM calls are unavailable for this work.
- Source-of-truth precedence is current code, then `CLAUDE.md`/`AGENTS.md`, then historical session material when not contradictory.
- Real product acceptance involving live Neo4j/OpenAI is separate from offline verification and must not run with placeholder credentials.

## Skill Registry

`.atl/skill-registry.md` exists and was read during initialization.

## SDD Operating Rules

- Artifact store: OpenSpec.
- Strict TDD: enabled for implementation phases.
- Delivery strategy: auto-chain.
- Chain strategy: stacked-to-main, selected after the tasks forecast recommended chaining.
- Review budget: 400 changed lines.
- If review-budget risk appears, split the work into chained review slices and resolve the chain strategy before apply.
- Keep implementation work units reviewable and include tests with the behavior they verify.
