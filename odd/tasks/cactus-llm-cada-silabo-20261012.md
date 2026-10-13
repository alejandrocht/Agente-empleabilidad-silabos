# LLM obligatorio por sílabo extraído

La solicitud requiere correr Administración a Psicología secuencialmente, sin HITL,
con análisis real del LLM. La política anterior omitía el modelo sin candidatos
literales o logros; el CLI aceptaba la omisión explícita como éxito.

Reproducción antes del cambio: `uv run --locked pytest -q
tests/unit/test_silabos_hab_tec.py tests/unit/test_cactus_llm_requerido.py -k
'sin_nombre_explicito or sin_candidatos_o_logros or sin_menciones_explicitas or
solo_un_silabo'`: **4 failed, 41 deselected**. Los dos casos del analista registraban
cero llamadas; los dos del CLI aceptaban publicaciones sin análisis completo.

El analista ahora invoca el modelo por cada sílabo único extraído, incluso con
candidatos vacíos. Los filtros y validaciones conservan máximo una habilidad,
nombre literal en la fuente y campos exactos del catálogo. Ninguna habilidad se
crea por exigir llamadas. El CLI exige respuestas con latencia para todos los
sílabos detectados; una respuesta vacía del modelo sigue siendo válida.

Verificación: `uv run --locked pytest -q tests/unit/test_silabos_hab_tec.py
tests/unit/test_cactus_llm_requerido.py tests/unit/test_cactus_secuencial.py
tests/unit/test_analista_tecnico.py`: **67 passed**. Incluye el servidor HTTP local
del CLI con 14 carreras secuenciales y un fallo intermedio, sin solapamientos.
Ruff focalizado y `git diff --check`: pasan.

Índice publicado tras pull d540eff: HABTEC_179ad280a3f043d1, 2190 registros,
1024 dimensiones, qwen3-embedding:0.6b, todas las 14 carreras; carga íntegra y
hash verificados sin descargar modelos ni consultar servicios externos.

Límite: las pruebas sustituyen el LLM y Cactus. La respuesta de los modelos y
credenciales reales de Windows se verifica al ejecutar el script allí.

Rollback: revertir este cambio en analista_tecnico.py, el contrato del CLI,
sus pruebas y el párrafo correspondiente del README. El catálogo nuevo queda intacto.
