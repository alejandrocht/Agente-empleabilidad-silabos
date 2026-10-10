# Comprobar análisis LLM en el corredor secuencial

Síntoma reportado en Windows: carreras terminan rápidamente con habilidades vacías.
El snapshot aportado de NOR_7c9bd075201c4181 aún dice `extrayendo`, con configuración
curricular y gate nulos. No confirma la configuración de una carrera ya terminada.

Reproducción antes del cambio:
`uv run --locked python -m pytest -q tests/unit/test_cactus_llm_requerido.py`
dio 2 failed, 1 passed. El CLI aceptaba `ALLOW_IMPORT` sin LLM habilitado o sin
sílabos con respuesta del modelo. Son escenarios de contrato reproducibles;
no prueban por sí solos la causa del runtime Windows.

Corrección: leer configuración efectiva del backend antes de pedir credenciales y
descargar; abortar si LLM está desactivado. Exigir evidencia de análisis completado
para marcar publicación correcta en el CLI. Mostrar sílabos con respuesta, omitidos
y propuestas válidas. Se admite una respuesta válida sin coincidencias, sin inventar.
`--diagnosticar` consulta IDs ya guardados y conserva estados, configuración,
conteos y hallazgos; no crea trabajos ni modifica los CSV. El nuevo GET de
configuración expone el mismo snapshot no secreto utilizado por las ejecuciones.

Verificación desde `backend`:
- Pruebas focalizadas del CLI, requisitos LLM y HAB_TEC: 41 passed.
- Runtime incluido: HTTP local de 14 carreras sin solapamiento; TestClient con
  configuración real desactivada aborta antes de credenciales/POST; worker Cactus
  con DOCX real, índice vectorizado de fixture y modelo aislado: desactivado produce
  cero llamadas/habilidades, activado una llamada y habilidad textual del catálogo.
- Suite completa: 672 passed, 1 warning previo de LangSmith.
- Ruff en archivos cambiados: All checks passed. Mypy de CLI/API, target 3.14: sin errores.
- CLI `--help`: exit 0. No servicios Cactus/Ollama reales ni secretos usados.

Pendiente: resultado de diagnóstico Windows para distinguir configuración desactivada,
logros/candidatos ausentes o error del proveedor. No se fuerza el modelo a responder
sin candidatos ni se alteran las aprobaciones o el vocabulario cerrado del catálogo.
Rollback: revertir este commit; afecta CLI, GET de configuración, pruebas y guía,
sin migración de datos ni cambios en el analista curricular.
