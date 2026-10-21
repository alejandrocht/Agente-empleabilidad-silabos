# Curate 2026-2 curricular sources

## Goal
Classify 2026-2 syllabi by the document's declared authority and `Nivel`, preserve original Cactus downloads, and record career-header disagreements for academic review before publishing a cross-career competency map.

## User constraints
- Syllabus `Nivel`, not the Cactus `Ciclo_XX` folder, determines curricular level. Where several levels exist, pair them via explicit parenthesized area/course-code markers; do not rely solely on position.
- The syllabus header determines its declared faculty/program/careers. Distinguish this authority from Cactus's observed career listing.
- Exclude Ingeniería Ambiental and Ingeniería Mecatrónica from the publishable mapping until their syllabi are defined; retain their paths in the discrepancy audit.
- Treat `CONTABILIDAD` and `CONTABILIDA Y FINANZAS` as candidate aliases of Contabilidad y Finanzas, retaining raw spelling for audit.
- Keep mismatch details in Markdown so faculty can resolve them. Preserve every original DOCX; do not move or replace them.
- No commit, push, Neo4j import, or code mutation without separate authorization.

## Source evidence
- `/Users/alejandromcht/Desktop/silabos`: 1,037 DOCX references in 14 careers; 168 General Studies appearances, 25 distinct General Studies documents (12 level one, 13 level two).
- Six non-General-Studies documents located in Cactus `Ciclo_02` have declared `Nivel` 5, 8/9, 9, or 9/10, never level 1 or 2.
- 24 Cactus-folder/header discrepancies across 13 unique documents; four are Contabilidad y Finanzas aliases or typos, the remaining 20 require policy/academic review. Ten appearances share one Seguridad, Salud Ocupacional y Bienestar Organizacional syllabus (level nine).

## Tasks
- [x] T1. Read-only inventory and verify the six false cycle-one/two classifications against first-table `Nivel` and explicit numeric tags.
- [x] T2. Create an exhaustive Markdown discrepancy dossier with all paths, codes, declared careers, declared levels, and dispositions; validate counts and source hashes.
- [x] T3. Create `ESTUDIOS_GENERALES/2026-2/Ciclo_01` and `Ciclo_02` from the 25 distinct syllabi classified by `PROGRAMA DE ESTUDIOS GENERALES` and declared level, without altering originals; record all source-career references.
- [ ] T4. After the academic scope policy is settled, generate an owner-scoped competency map and per-career coverage preserving competency–outcome references; exclude the two provisional careers from publication and keep discrepancies auditable.

## Acceptance criteria
- No non-General-Studies source is copied into Estudios Generales merely because Cactus placed it in `Ciclo_01` or `Ciclo_02`.
- All 24 mismatched appearances and four aliases are individually traceable in Markdown, including excluded careers.
- Any generated competency mapping distinguishes source-owner scope from a consuming career, and retains unresolved references without invented edges.
- Original DOCX files and existing catalog outputs remain unchanged.

## Progress
- T1 verified: all six apparent Ciclo_02 non-EG files declare different levels. For Proyecto de Videojuegos, tags (65)/(55) explicitly pair Noveno/Décimo with corresponding course codes; positional ordering alone was not used.
- T2 complete: `Desktop/silabos/DISCREPANCIAS_2026-2.md` records 24 numbered appearances in 13 content groups and six non-EG Ciclo_02 occurrences. Structural check: 30 referenced paths exist, 24 rows numbered continuously, and all 24 source XML hashes match the dossier; 4 accepted Contabilidad aliases, 9 excluded Ambiental/Mecatrónica paths, 11 pending other career placements.
- T3 complete: `Desktop/silabos/ESTUDIOS_GENERALES/2026-2` contains 12 copies with declared Nivel Primero and 13 with declared Nivel Segundo. `README.md` records course codes, observed career folders, and chosen original paths for all 25; 168 original appearances were grouped by source XML. Verification checked every copied file's SHA-256 against its original and confirmed the manifest matches exactly 25 outputs, with no unexpected files or level mismatches.
- T4 corrected provisional deliverable: `Desktop/silabos/MAPA_COMPETENCIAS_UNICAS_POR_CARRERA_2026-2.csv` retains the same 200 unique career/code/name rows and the first five columns (`carrera,tipo,codigo,nombre,estado_codigo`), now with `descripcion,cantidad_descripciones,estado_descripcion` appended (eight columns total). The 200 rows comprise 133 G and 67 E across 12 publishable careers plus Estudios Generales (eight G) as the thirteenth. It contains NO course or outcome links. Every mapped row has a syllabus description; 132 rows have one distinct normalized description and 68 show 2–5 numbered full-text variants marked `REVISAR_DESCRIPCIONES_DISTINTAS` (including four of the eight EG rows). The preceding five-column file is preserved in `Desktop/silabos/_versiones_anteriores_2026-2/MAPA_COMPETENCIAS_UNICAS_POR_CARRERA_2026-2_SIN_DESCRIPCIONES.csv`; independent verification confirmed exact parity of its 200 rows, status flags, and all new descriptions. It flags 44 `(carrera,codigo)` groups with different normalized names (101 rows) for academic review; e.g. Arquitectura G1 is both Pensamiento crítico and Pensamiento sistémico, while EG G1–G8 have no name overlaps. Crucial correction: 74 E rows in shared syllabi have a fourth cell identifying the actual career; E1 Ética contable is assigned to Contabilidad y Finanzas, NOT Administración/Marketing merely because they share a syllabus. Eight E rows in shared multi-career syllabi lack a row-level career, and five row-level career references disagree with the syllabus header; those associations were not assigned speculatively. Eight section-vs-code G/E disagreements also warrant review. A targeted row-career parser check and an independent verifier passed the 200-row/13-career/44-conflict/no-relations assertions. The earlier 421-row career catalog and 4,791-row outcome coverage had blind shared-E fan-out, were WRONG for per-career use, and have been moved out of the root into `Desktop/silabos/_generados_superados_2026-2/`; do not use them for academic mapping.
- User clarified that the 27 distinct paths explicitly listed in the exception CSV must be **copied, not moved**. `Desktop/silabos/silabs_errores/<original path>` contains 27 byte-identical copies; `silabs_errores/ORIGENES_2026-2.csv` records source/copy/SHA-256 and was independently verified. Originals and curated EG files are intact; three copied documents have further identical original copies in other career folders.
- Academic resolution remains pending: `AUDITORIA_CODIGOS_COMPETENCIAS_2026-2.csv` lists 18 candidate rows without numeric G/E/C in 10 syllabi, 16 syllabi without parseable competency rows, and C7/C8 from EG Filosofía Aplicada. The corrected eight-column map also excludes eight multi-career E rows lacking an explicit row-level career and five row/header career contradictions; these require faculty review before calling the map exhaustive. G7/G8 were not inferred from C7/C8, and 11 other Cactus/header associations in `DISCREPANCIAS_2026-2.md` still need confirmation. T4 remains unchecked as a final academic map; nothing was imported to Neo4j.
- No commits, Neo4j imports, or source DOCX changes. Engram mirror unavailable until provider compatibility is restored.
