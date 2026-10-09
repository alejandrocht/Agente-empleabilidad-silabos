# Integración de main y test — 2026-10-09

Autorización: fusionar main y test/local-llm-technical-pipeline y publicar ambas ramas.

## Fusión

Base main: f09bfd06a47ed1846b33fc29f3760e3dd42c95a7.
Base test: a89a875 (historia técnica previa, mayormente incorporada mediante rebase).
Se revisaron los once archivos en conflicto y se conservaron las correcciones
posteriores de main: carga/vectorización, configuración LLM, persistencia segura,
importación y pruebas. La fusión no cambia comportamiento de producción.
Se independizaron los fixtures de pruebas del archivo .env local ignorado y se
actualizaron los mocks de LangSmith y la expectativa del modelo predeterminado.

Validación: backend limpio, 574 pruebas; frontend, 98 pruebas y build Next.js.
Harness de ejecución: N/A para esta fusión de historia y fixtures; sin servicios externos.
Reversión: revertir este merge con parent 1, preservando los cambios posteriores.

## Importación compatible con HAB_TEC

El contrato de seis CSV importa habilidades y sus coberturas; conserva IDs
numéricos de longitud variable, incluida HAB_TEC_007. Las habilidades publicadas
por el catálogo se comparan con el nombre/descripción del contexto de la carrera,
no con el nombre global que puede pertenecer a otra carrera. El writer no cambia
los nodos existentes del catálogo.
Validación: pytest -q tests/unit/test_neo4j_catalogos.py tests/unit/test_neo4j_importador.py:
16 passed. Ruff check: passed.
Harness: escenarios de preview/importación/reversión con FakeDriver; 16 passed,
incluidas diferencias de nombre, descripción y carrera. Sin escritura Neo4j real.
Reversión: revertir el commit de neo4j_catalogos.py, neo4j_importador.py y sus dos
tests para retirar el soporte de habilidades; hacerlo junto con el cambio de
vocabulario cerrado si se requiere volver al flujo anterior.

## Habilidades exactas del catálogo vectorizado

La ejecución LLM carga la última versión HAB_TEC completamente vectorizada,
recupera candidatos por logro y carrera usando el modelo del índice y mantiene
el vocabulario cerrado. Python copia ID/nombre/descripción oficiales y valida
otra vez antes de materializar. Las propuestas fijan catálogo y SHA para
aprobaciones posteriores. Se deduplica por sílabo y referencia; una selección
vacía es válida y no fuerza habilidades inventadas. Se sustituyeron los tests
de creación libre por pruebas de rechazo y de campos exactos.
Validación focal: pytest -q tests/unit/test_analista_tecnico.py
 tests/unit/test_silabos_hab_tec.py tests/unit/test_salida_catalogos.py
 tests/unit/test_post_hitl_workflow.py: 65 passed.
Validación global hasta esta unidad: 598 passed; Ruff check passed.
Harness: test_silabos_hab_tec crea un XLSX, lo carga/vectoriza con el gestor,
infiere contra el índice y exporta CSV; post_hitl verifica aprobación,
importación y reversión. Embeddings/LLM/Neo4j simulados, sin servicios externos.
No hay artefactos reales del catálogo/vectorización en este checkout; se
seleccionan del almacenamiento local de la PC donde se cargaron.
Reversión: revertir esta unidad retira retriever validado, analista cerrado,
validación de salida/HITL y el filtro de auditoría informativa en limpieza.
No toca documentos ni CSV históricos.

## Hashes de los cuatro cursos auditados

La identidad distingue código observado + carrera + nombre solo para los cuatro
cursos señalados. Sus contrapartes conservan el hash anterior. DOCX y PDF
comparten regla; no se altera codigo_curso ni se asume el código del plan.
Validación focal: pytest -q tests/unit/test_ids_cursos_auditados.py
 tests/unit/test_normalizador_silabos.py: 43 passed (17 casos auditados).
Harness: extracción de DOCX generados y exportación de los seis CSV, referencias
regeneradas de curso/sílabo/logro/cobertura; PDF con lector simulado. Passed.
Reversión: retirar la excepción en extraccion_curricular.py y el argumento de
nombre en extraccion_pdf.py junto con su test; no hay migración del grafo.
Las ejecuciones anteriores deben regenerarse para aplicar los nuevos hashes.

## Verificación final antes del push

Backend en checkout limpio: uv run --locked --extra dev pytest -q: 615 passed,
1 warning de deprecación de LangSmith. Frontend sin cambios respecto de main:
98 tests passed y next build passed. Ruff en los módulos/tests modificados: passed.
Mypy: --python-version 3.14 --follow-imports silent en los nueve módulos
modificados: Success, no issues found. La invocación con configuración base 3.11
choca con stubs NumPy instalados en Python 3.14; seguir imports con 3.14 reporta
cinco errores existentes en logger, prompt_injection y constructor (fuera de scope).
Los archivos locales pendientes ajenos a estas unidades se conservaron en el
checkout original; no se publican .env, outputs ni artefactos locales del catálogo.
