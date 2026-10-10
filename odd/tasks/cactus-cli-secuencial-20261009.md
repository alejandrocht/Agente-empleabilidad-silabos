# Corrida Cactus por carrera desde terminal

Solicitud: ejecutar de Administración a Psicología, sin depender del frontend.

`backend/scripts/normalizar_cactus_secuencial.py` usa el contrato HTTP existente.
Solicita una carrera, espera su descarga y análisis LLM hasta un estado terminal,
y entonces solicita la siguiente. Un error terminal no corta las otras carreras.
Cada carrera conserva su ID y su paquete independiente sujeto al release gate.
Usuario/contraseña se piden una vez; la contraseña se oculta y no se persiste.
Los snapshots y el resumen quedan en `backend/resultados_cactus/`, ignorado por Git.
No se reintentan POST sin respuesta. Una interrupción, pérdida de conexión o estado
desconocido detiene la secuencia y conserva el ID conocido para revisar el backend.

Verificación desde `backend`:
- `uv run --locked python -m pytest -q tests/unit/test_cactus_secuencial.py`: 7 passed.
- Runtime HTTP real local incluido en la prueba: servidor de prueba con 14 carreras,
  estados extracción/LLM/final, Arquitectura falla, otras 13 permiten publicación;
  ningún POST mientras el trabajo anterior está activo, JSON sin credenciales.
- `uv run --locked python -m pytest -q`: 665 passed, 1 warning previo de LangSmith.
- Ruff sobre script y prueba: All checks passed. Mypy del script, target 3.14: sin errores.
- CLI `--help`: exit 0. `git diff --check`: sin errores.

No se verificó Cactus real ni Ollama en Windows. El script usa la configuración
existente del backend; no corrige una autenticación o análisis fallido.
Rollback: eliminar el script, su prueba y esta nota, el párrafo CLI del README
y la entrada `backend/resultados_cactus/` de `.gitignore`; no modifica la API ni el frontend.
