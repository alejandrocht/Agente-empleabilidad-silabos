# Canonical normalizer execution page

## Goal

Move every live and historical normalization run to a canonical `/{NOR_id}` frontend URL with automatic stage panels, without changing the backend or local-LLM pipeline.

## Constraints

- Do not modify backend code, Ollama configuration, prompts, inference, extraction, HITL semantics, or CSV generation.
- Preserve all unrelated tracked and untracked work.
- Reuse the existing execution polling and approval modules.
- Keep legacy inspection URLs working through a redirect.

## Tasks

- [x] Add the validated canonical `/{NOR_id}` route and legacy redirect.
- [x] Navigate new and restored executions plus history links to the canonical URL.
- [x] Split the execution view into Progress, Review, CSV, Neo4j, and Audit panels.
- [x] Render declared CSV downloads, metadata, and bounded previews.
- [x] Update focused frontend tests and run the production build.
