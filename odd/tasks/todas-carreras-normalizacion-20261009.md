# Normalización de todas las carreras — 2026-10-09

## Resultado

El selector Carrera ofrece Todas las carreras (API: TODAS), para una ejecución y
un único paquete curricular de seis CSV del periodo seleccionado.

- Cactus recorre secuencialmente las 14 carreras y descarga bajo carrera/periodo.
  Acumula el progreso, conserva cancelación y detiene errores de autenticación.
  Una carrera fallida o parcial bloquea publicación, aunque los conteos de las demás coincidan.
- La carga manual exige ZIP con carrera explícita en las carpetas. Se procesan
  solo las carreras presentes; se rechazan carpetas ambiguas y periodos mezclados.
  Admite hasta 7000 sílabos con los límites de tamaño originales.
- El análisis conserva la carrera concreta de cada sílabo y utiliza su selección
  vectorizada. Nombres, descripciones e IDs deben ser idénticos al catálogo vigente
  de la propuesta, también al aprobar/materializar.
- Los cursos con ID compartido entre carreras reciben CUR/SIL distintos antes del
  análisis; staging, progreso, revisión y cobertura usan esos mismos IDs.
  Los códigos fuente y los IDs de cursos sin colisión se conservan.
  Esto no migra cursos ya importados desde ejecuciones individuales.
- Una habilidad global compartida conserva su fila exacta por carrera. Los seis
  archivos se validan también con el lector del importador, sin escribir en Neo4j.

## Verificación

Desde backend:

- `rtk uv run --locked --extra dev pytest -q tests/unit/test_todas_carreras.py tests/unit/test_silabos_hab_tec.py`: **54 passed**.
- `rtk uv run --locked --extra dev pytest -q`: **650 passed**, un aviso de
  deprecación previo de LangSmith.
- Ruff sobre los cinco módulos modificados y las dos pruebas modificadas/nuevas:
  **All checks passed**.
- Mypy sobre esos cinco módulos, con
  `--python-version 3.14 --follow-imports silent`: **sin errores**.
- `rtk uv run --locked python -m compileall -q agente api scripts`: **exit 0**.

Desde frontend:

- `rtk npm test -- src/components/NormalizadorPanel.test.jsx`: **9 passed**.
- `rtk npm run check`: **101 passed**, compilación de producción correcta.

Harness de API:
`test_api_multicarrera_normaliza_aprueba_y_publica_un_solo_paquete` realiza POST
multipart real mediante TestClient, ejecuta el Future completo, usa un índice
vectorizado de prueba y un LLM sustituido explícitamente, aprueba con HITL=0 y
consulta GET de la ejecución. Verifica dos carreras, una ejecución, CUR/SIL
distintos, campos exactos del mismo ID global en ambas carreras, progreso coherente,
ALLOW_IMPORT y aceptación de los seis CSV por el lector del importador: **PASS**.

Harness de navegador: skill webapp-testing, helper with_server.py con Next dev en
5071 y `/tmp/ciar-todas-carreras-ui-20261009.py`, Playwright Chromium. Historial vacío
sustituido mediante route; no credenciales ni conexiones a Cactus/Neo4j.
Selección TODAS en Cactus/manual, rechazo de DOCX individual y diseño a 1280/390px:
**PASS**, sin errores JavaScript ni desborde horizontal. Capturas locales:
`/Users/alejandromcht/Desktop/PRUEBA NEO4J/tmp/todas-carreras-ui/`.

No se ejecutó una descarga real de las 14 carreras ni se midió Ollama con el
hardware de la otra PC. Las pruebas usan datos aislados; no modifican el XLSX fuente
ni los .env. La otra PC necesita su catálogo vectorizado local disponible.

## Controles generales pendientes anteriores al cambio

`ruff check .` detecta 25 problemas en módulos ajenos al cambio
(dashboard/servicio.py, utils/prompt.py, utils/schema_ciar.py,
scripts/importar_docs_ontologia.py y tests/test_entity_resolution_static_schema.py).
El comando general `mypy agente api` se interrumpe al interpretar los stubs de
NumPy para Python 3.12+ con la versión objetivo 3.11 del proyecto. El chequeo de los
módulos tocados con la versión instalada 3.14 pasa.

## Unidad de entrega y reversión

La opción multicarrera se entrega con sus pruebas y documentación en una unidad
funcional; supera 400 líneas de cambios escritos, principalmente pruebas de
procedencia, cobertura e integración. La publicación directa está autorizada por
el usuario; no se comprimieron ni omitieron pruebas para reducir el diff.

Revertir esta unidad elimina TODAS de entrada.py, limpieza.py,
extraccion_curricular.py, fuente_cactus.py y salida_catalogos.py, el selector/help
en NormalizadorPanel.jsx, las pruebas correspondientes y el párrafo de backend/README.md.
No necesita revertir el catálogo cerrado, los cuatro cursos auditados, la fusión
previa ni cambios personales pendientes del checkout original.
