# Evidencia de una extracción Cactus abortada

En NOR_13f7145f46734243, el progreso mostraba 86 descargas y Arquitectura como
carrera actual, pero fuente solo contenía código/detalle de error. La finalización
purgaba la carpeta de descargas antes de construir el ZIP de entrada.

El registrador de errores ahora conserva los campos de progreso no sensibles,
marca completa=false y respalda los PDF/DOCX descargados en entrada/<archivo>
antes de la purga. fuente.archivo_parcial identifica el ZIP interno y
archivos_procesables indica su número de documentos. Si el respaldo falla, se
conserva el error original y se añade respaldo_parcial_error con el tipo de fallo.
No se inicia análisis LLM ni se publica cobertura incompleta. El contrato público
de seis CSV permanece sujeto a ALLOW_IMPORT; el respaldo es accesible desde disco.

La conservación comienza con esta versión; no reconstruye descargas de ejecuciones
antiguas cuyos temporales ya se purgaron.

Verificación:

- Antes, test_fallo_en_segunda_carrera_conserva_conteos_y_zip_parcial_sin_credenciales
  fallaba con KeyError: completa. Después pasa.
- Desde backend:
  `rtk uv run --locked --extra dev pytest -q tests/unit/test_cactus_error_evidencia.py`:
  **2 passed**.
- Harness del runner real: primera carrera con 86 archivos, segunda con fallo de
  autenticación; verifica manifest/GET, conteos, ZIP de 86 archivos de
  ADMINISTRACION/2026-2, error terminal, ausencia de LLM/salidas publicadas y purga
  de perfil/cookies, sin usuario ni contraseña persistidos: **PASS**.
- Respaldo con fallo de disco: conserva CACTUS_AUTENTICACION_FALLIDA: **PASS**.
- Conjunto final backend: **658 passed**, aviso previo de deprecación de LangSmith.
- Ruff de módulos y pruebas modificados: **All checks passed**; mypy de los dos
  módulos modificados, con versión objetivo 3.14 y follow-imports silent: **sin errores**;
  compileall: **exit 0**.

Reversión independiente: quitar el respaldo y la copia de conteos de
ejecuciones_curriculares.py, test_cactus_error_evidencia.py y el párrafo de README.
Conserva el arreglo del navegador único, TODAS, catálogo y hashes existentes.
