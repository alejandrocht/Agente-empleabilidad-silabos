# Sesión de Cactus durante el recorrido multicarrera

La ejecución Windows NOR_13f7145f46734243 terminó en error al pasar de
Administración a Arquitectura (2/14), tras 86 descargas. El reporte indica
CACTUS_AUTENTICACION_FALLIDA; el análisis LLM no había empezado.

Antes, TODAS invocaba extraer de nuevo por carrera, cerrando y reabriendo Chrome
con el mismo directorio de perfil. Un perfil persistente no garantiza conservar
cookies de sesión al cerrar el navegador. Se separó la descarga de una carrera
del ciclo de vida del navegador: extraer abre un contexto para la ejecución, las
14 carreras lo comparten y finally lo cierra al terminar, fallar o cancelarse.
El error de autenticación también identifica carrera y posición.

Reproducción mínima: la prueba
test_multicarrera_conserva_sesion_al_pasar_a_la_segunda_carrera usa el extraer real
y la recuperación de autenticación real, con una sesión controlada que deja de
funcionar al reabrir el navegador. Antes falla con el mismo texto del reporte
Windows; después pasa con dos carreras y con las 14.

Verificación desde backend:

- `rtk uv run --locked --extra dev pytest -q tests/unit/test_normalizador_cactus.py tests/unit/test_todas_carreras.py`: **44 passed**.
- `rtk uv run --locked --extra dev pytest -q`: **658 passed** en el conjunto final,
  con un aviso previo de deprecación de LangSmith.
- Ruff sobre los módulos y pruebas modificados: **All checks passed**.
- Mypy de fuente_cactus.py y ejecuciones_curriculares.py con
  --python-version 3.14 --follow-imports silent: **sin errores**.
- compileall de agente/api/scripts: **exit 0**.

Harness adicional con Chromium real y servidor HTTP local, cookies de sesión sin
Expires, login y página protegida reales. Listado y descargas se sustituyen con
fixtures. Archivo local de diagnóstico:
`/Users/alejandromcht/Desktop/PRUEBA NEO4J/tmp/debug-cactus-sesion-20261009/session_harness.py`.
Invocación desde backend: `rtk proxy uv run --locked python <ruta> --before`
reproduce la versión 62bbb8a y falla con **logins=2, contextos=2** y
CACTUS_AUTENTICACION_FALLIDA. Sin --before: **PASS**, carreras=14, logins=1,
contextos=1. No se enviaron credenciales a sitios externos.

La pérdida de sesión por reiniciar el navegador queda confirmada en la
reproducción. No se ejecutó Cactus real ni se accedió a la PC Windows: la nueva
corrida allí debe validar el arreglo contra el servicio. Las hipótesis de
redirección tardía y rechazo externo del login permanecen fuera de esta prueba.

Reversión independiente: fuente_cactus.py, las pruebas de sesión/recursos de
test_normalizador_cactus.py, la adaptación del seam en test_todas_carreras.py y la
frase de README sobre un navegador por ejecución. Conserva TODAS, catálogo cerrado
y hashes existentes. El registro de evidencia de errores es otra unidad.
