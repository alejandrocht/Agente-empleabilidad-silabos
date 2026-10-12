# Una habilidad explícita por sílabo

Requisito: retirar la copia histórica extraída, no inferir habilidades implícitas,
y conservar como máximo una habilidad técnica por sílabo. Se eliminaron exclusivamente
`tmp/recuperacion-chh-embeddings-20261012/embeddings.py` y `origen.json` fuera del repo.

La política del producto `extraccion_explicita_max_1` exige el nombre completo del
catálogo en logros o programa analítico. Solo normaliza caso, tildes y espacios para
reconocer la mención; no usa sinónimos. Filtra antes de consultar embeddings, revalida
la mención al materializar/exportar, limita el esquema LLM a una propuesta y rechaza
dos referencias distintas para el mismo sílabo aun aprobadas. Los cargadores históricos
explícitos de herramientas offline mantienen su compatibilidad; la API usa HAB_TEC.
Las omisiones por ausencia de mención se auditan y el CLI acepta ese resultado vacío
cuando está completado y permitido por el gate; no fuerza habilidades ni llamadas LLM.

Durante el trabajo llegó `cc554bc`, con empleabilidad restaurada y el catálogo
HABTEC_1ec89ed7cf9a4ccc. Se integró por fast-forward sin sobrescribir cambios del usuario.
Se actualizaron tres aserciones obsoletas al contrato restaurado de API/manifests.
El índice se copió al checkout original: 6 archivos idénticos, 1898 vectores,
1024 dimensiones, 14 carreras, modelo qwen3-embedding:0.6b.

Verificación: suite backend 685 passed (1 warning previo de LangSmith); focales
HAB_TEC/post-HITL/CLI 60 passed antes de integrar cc554bc; pytest completo repetido
tras integrar el contrato restaurado. Ruff de archivos modificados y mypy de cuatro
módulos target 3.14 sin errores. Frontend `npm run check`: 101 passed y build correcto.
Runtime: DOCX real e índice fixture con selección LLM aislada, API de aprobación
rechaza una mención ausente y revierte manifest/journal/CSV. Índice publicado cargado
por el retriever real con SHA validado. Se descargó Qwen y una consulta real produjo
1024 dimensiones, coseno 0.99974706 frente al vector guardado y 8 candidatos.
La descarga terminó antes de la aclaración del usuario de hacerlo en la otra PC.
Se cerró el servidor Ollama iniciado para esta comprobación; no se descargaron otros modelos.

Rollback: revertir este commit de política/tests/documentación. No elimina el catálogo
publicado por cc554bc ni migra ejecuciones existentes. No se normalizaron sílabos reales
ni se modificó Neo4j. La extracción textual estricta puede producir menos coincidencias.
