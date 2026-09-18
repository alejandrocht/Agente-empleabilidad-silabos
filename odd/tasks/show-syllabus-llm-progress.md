# Show per-syllabus LLM progress

## Objective

Expose the existing curricular execution progress in the frontend at syllabus granularity, including model-analysis percentage, extraction state, latency, and individual progress without duplicating polling or execution logic.

## Scope

- Extend the existing `progreso_llm` snapshot with metadata-only per-syllabus trace rows.
- Reuse `NormalizadorPanel` execution polling and normalize optional trace data defensively so older manifests remain usable.
- Render an accessible per-syllabus progress list with aggregate counters and latency.
- Add focused component tests for complete, partial, and unavailable traces.

## Non-goals

- Do not change Cactus extraction behavior.
- Do not expose prompts, secrets, full model responses, or sensitive syllabus content.
- Do not add a second polling endpoint or duplicate backend execution logic.

## Tasks

- [x] Define the trace contract and frontend adapter for optional syllabus progress data.
- [x] Add the per-syllabus progress panel to the existing LLM activity section.
- [x] Add regression tests for percentage, latency, extraction, and incomplete data.
- [x] Run focused backend/frontend tests, Ruff, Mypy, and the frontend build.

## Acceptance criteria

1. The panel shows aggregate analyzed/total percentage and per-syllabus percentage when trace data exists.
2. Each syllabus row can show extraction state, model state, latency, and progress without exposing model content.
3. Existing manifests without per-syllabus traces render the current aggregate UI unchanged.
4. Tests cover normal, partial, and missing trace data.
