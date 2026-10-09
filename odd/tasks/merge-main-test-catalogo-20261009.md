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
