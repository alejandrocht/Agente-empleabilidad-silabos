# Track 2026-2 competency source discrepancies

## Goal
Create one public, sanitized GitHub issue asking academic owners to reconcile the 2026-2 syllabus competency catalog before any correction or Neo4j import.

## Authorization and boundaries
- User explicitly approved a public YAML Issue Form commit on `main` and a sanitized public issue in `alejandrocht/Agente-empleabilidad-silabos`.
- Do not publish the local CSV, full syllabus descriptions, personal file paths, DOCX content, credentials, or unverified academic conclusions.
- Preserve local DOCX originals and existing CSV evidence. This work creates no Neo4j import or source-data fix.
- The target's default branch originally lacked a YAML Issue Form; the new form `academic-data-discrepancy.yml` is now published and verified on `main`.

## Tasks
- [x] Verify exact public target, authenticated actor, repository issue capability, and explicit disclosure/authorization.
- [x] Add a minimal YAML Issue Form on the target default branch and verify the published commit and form content. Published `main` commit `ba837f91a660911307a89760c6dd104d37522fd5`; target-host readback matched the four-required-textarea YAML byte-for-byte.
- [x] Search open and closed issues after the form is available; the complete target-host listing (`--state all --limit 1000`) returned zero issues, so there is no existing equivalent to reuse.
- [x] Publish one sanitized, source-evidenced issue and verify target-host readback: [issue #10](https://github.com/alejandrocht/Agente-empleabilidad-silabos/issues/10), OPEN, no labels; exact title and body matched after newline normalization. One create attempt, no retry.

## Evidence available locally
- `MAPA_COMPETENCIAS_UNICAS_POR_CARRERA_2026-2.csv`: 200 career/code/name rows, 13 scopes including General Studies; 44 career+code groups have different names, 68 rows have multiple normalized descriptions.
- Only Administration lacks G6 within observed G1–G8; no G6 cell appears in 73 distinct syllabi whose header declares Administration. General Studies declares G6 separately in five syllabi.
- `AUDITORIA_CODIGOS_COMPETENCIAS_2026-2.csv`: 18 candidate rows without numeric G/E/C, 16 syllabi without parseable competency rows, and C7/C8 in one General Studies syllabus.
- Eight multi-career E rows have no row-level career; five row-level career labels contradict the syllabus header. These are source-policy questions, not confirmed extractor bugs.

## Acceptance
- Public issue body contains aggregate evidence, limited non-sensitive examples, explicit questions and owner decisions needed; it does not disclose the local CSV or private paths.
- No code or source DOCX is changed to guess missing codes, descriptions, or ownership.
- Published issue: https://github.com/alejandrocht/Agente-empleabilidad-silabos/issues/10 (confirmed target-host readback; no labels). Privacy preflight found no local paths, attached CSV/DOCX filenames, credentials or full syllabus descriptions in the public body. One create attempt; no retry.
