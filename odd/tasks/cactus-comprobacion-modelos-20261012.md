# Comprobación antes de la corrida secuencial

El CLI consulta la configuración efectiva del backend y prueba, antes de pedir
credenciales Cactus, el catálogo vigente, su cobertura de las 14 carreras, el modelo
embedding del índice y una respuesta estructurada del analista. La prueba utiliza
el mismo analista y fábrica del flujo real, no solo una bandera habilitada. No
crea ejecuciones, descarga modelos, vectoriza ni publica en Neo4j.

`--comprobar` permite verificar solo esta preparación. La corrida normal guarda
`comprobacion.json`, continúa con HITL 0 y conserva la comprobación de una respuesta
LLM por cada sílabo detectado. Los errores identifican catálogo, embeddings o LLM,
sin devolver mensajes crudos de proveedores ni secretos.

Verificación focalizada: `uv run --locked pytest -q
tests/unit/test_silabos_hab_tec.py tests/unit/test_cactus_llm_requerido.py
tests/unit/test_cactus_secuencial.py`: **58 passed**.
Runtime: el caso `test_comprobacion_usa_http_real_del_analista_y_embedding` levanta
un servidor HTTP compatible, recibe `/api/embed` con el modelo del índice y
`/v1/chat/completions` con el modelo curricular, y valida el contrato JSON Schema.
El CLI también se prueba contra un servidor HTTP con 14 ejecuciones sin solapamiento.

Suite completa: `uv run --locked pytest -q`: **692 passed**, una advertencia previa
de deprecación de LangSmith. Ruff focalizado y `git diff --check`: pasan.
Mypy con `--python-version 3.14 --follow-imports=silent` sobre los tres módulos
modificados: pasa. Con seguimiento completo hay cinco errores en módulos ajenos
(logger.py, prompt_injection.py y constructor.py); no se modifican aquí.

Límite: servidor compatible y fixtures de catálogo aislados en pruebas. Ollama y
Cactus de Windows se verifican al lanzar el script en esa PC. No se descargaron
modelos locales para este cambio.

Rollback: quitar la ruta `/configuracion/curricular/comprobar`, la llamada inicial
del CLI y sus pruebas/documentación. La exigencia de LLM por sílabo y el catálogo
publicado no dependen de esta comprobación y permanecen intactos.
