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
