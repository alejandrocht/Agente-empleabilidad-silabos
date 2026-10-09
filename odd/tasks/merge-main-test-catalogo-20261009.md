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
