# Rank 2026-2 competency variants with syllabus provenance

## Goal
Provide academic reviewers a provisional plurality by career and G/E code, plus every name/description variant with the source syllabus names and paths. Do not change the already approved 200-row competency map or declare a plurality to be academically correct.

## Boundaries
- Count one vote per distinct DOCX document XML within a career+code+variant. Original Cactus duplicates and the 27 `silabs_errores` copies do not contribute another vote.
- Preserve Estudios Generales as a separate scope; allocate multi-career E rows only to the careers named in their own cells. Leave eight unscoped E rows and five row/header career contradictions unresolved.
- A tied name has no selected name or description. A tied description under a uniquely selected name has no selected description.
- Keep missing numeric codes and wholly unparseable DOCX in the existing exception audit; frequency cannot assign their code.
- Produce local CSVs only. Do not upload syllabi/CSV to the public GitHub issue or import Neo4j.

## Tasks
- [x] Audit current 200-row map, 27-copy error manifest, and unique DOCX frequency units. Found 143 career+code groups, 301 name/description variants, two name ties and seven description ties.
- [x] Generated `Desktop/silabos/RESUMEN_MAYORIAS_COMPETENCIAS_2026-2.csv` (143 career+code rows) and `Desktop/silabos/EVIDENCIA_VARIANTES_COMPETENCIAS_2026-2.csv` (301 name+description variants) with distinct-DOCX vote counts, syllabus titles, and absolute original/curated/error-copy paths. The prior 200-row CSV was not overwritten.
- [x] Deterministic checks passed: approved source CSV SHA-256 remains `a86b07891ac41765925980fb19f90f730b6f9a53b8b0995150711defc13592cb`; all 200 career+code+name keys appear in the detail CSV, 143 summary groups are unique, all cited paths exist and error-copy paths belong to the 27-row manifest. Two name ties and seven description ties have no selected winner. Arquitectura G1 has 13 distinct DOCX for Pensamiento sistémico vs one for Pensamiento crítico. Only five of the 27 copied error DOCX have an attributable coded G/E declaration in these variants; the other 22 remain in the exception audit/manifest, not forcibly assigned. The auxiliary verifier failed without evidence; the exact bounded checks were rerun directly and passed.

## Acceptance
- Current `MAPA_COMPETENCIAS_UNICAS_POR_CARRERA_2026-2.csv` stays byte-for-byte unchanged.
- Every variant's vote count equals the number of distinct source XML digests, not file appearances; every published path exists.
- Reviewers can filter provisional winners, disagreements, ties, and the precise syllabus source for each variant without accepting a fabricated academic equivalence.
