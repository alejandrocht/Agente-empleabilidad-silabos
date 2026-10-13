# Catálogo vectorizado rechazado después del pull en Windows

La comprobación ocultaba los errores del lector bajo «falta un catálogo vectorizado
válido con las 14 carreras». El bundle publicado sí contiene las 14 carreras.

Reproducción: `uv run --locked pytest -q tests/unit/test_silabos_hab_tec.py -k crlf`
antes del arreglo: **1 failed, 1 passed**. Convertir solamente LF a CRLF en el JSONL
produce «El índice no corresponde al catálogo HAB_TEC vigente» porque se comparan
hashes de bytes. El test también comprueba que cambiar IDs debe seguir fallando.

Arreglo: `.gitattributes` impide convertir los artefactos HAB_TEC. Para checkouts
anteriores, el lector intenta recuperar el SHA esperado sustituyendo únicamente
CRLF por LF cuando el hash original no coincide. Mantiene validaciones de datos,
metadatos, dimensiones, carreras y vectores. No escribe ni revectoriza el catálogo.

La API/CLI ahora diferencian catálogo ausente, hash distinto, archivos incompletos
o ilegibles y carreras concretas ausentes, sin publicar excepciones de proveedores.

Runtime: repo Git temporal con el bundle real de 2190 registros y
`core.autocrlf=true`. Checkout sin atributos produjo CRLF y hash bruto diferente;
el nuevo lector recuperó el SHA original. Con `.gitattributes`, el checkout devolvió
exactamente los bytes originales. Sin llamadas a Ollama ni descarga de modelos.

Verificación focalizada: `uv run --locked pytest -q tests/unit/test_silabos_hab_tec.py
tests/unit/test_cactus_llm_requerido.py tests/unit/test_cactus_secuencial.py`:
**66 passed**. Suite completa: **700 passed**, una advertencia previa de LangSmith.
Ruff, diff-check y mypy focalizado con follow-imports=silent pasan.

Límite: el fallo CRLF está reproducido con Git real, pero no se ha inspeccionado la
configuración de la PC Windows del usuario. Una carpeta configurada distinta o un
catálogo local posterior también pueden causar el mensaje genérico anterior; los
nuevos diagnósticos los distinguen. La comprobación falla antes de crear trabajos.

Rollback: atributos de HAB_TEC, normalización limitada del hash y diagnóstico
API/CLI con sus pruebas/documentación. No cambia catálogo, vectores ni reglas LLM.
