"""Validación determinista y exposición HITL de salidas curriculares."""

from __future__ import annotations

import csv
from pathlib import Path

from agente.normalizador.empleabilidad.catalogo import clave_concepto
from agente.normalizador.modelos import Hallazgo
from agente.normalizador.silabos.integridad_chh import validar_integridad_chh
from agente.normalizador.silabos.release_gate import (  # noqa: F401
    _validar_pendientes_fuente,
    evaluar_release_gate,
)
from agente.normalizador.silabos.resolucion_curricular import (
    _declaraciones_de_registros,
    _logros,
    _texto,
)

COMPETENCIAS_SCHEMA: tuple[str, ...] = (
    "id_competencia",
    "nombre_competencia",
    "descripcion_breve_competencia",
    "tipo_competencia",
    "codigo_competencia",
)
CURSOS_SCHEMA: tuple[str, ...] = (
    "id_curso",
    "nombre_curso",
    "coordinador",
    "creditos",
    "nivel",
    "tipo_curso",
    "codigo_curso",
    "id_carrera",
)
SILABO_SCHEMA: tuple[str, ...] = (
    "id_silabo",
    "codigo_silabo",
    "sumilla",
    "id_curso",
)
# The published entity is the learning outcome, not the canonical skill, so
# this table keeps its historical constant name while carrying the outcome
# columns consumed by ``catalogo_logros.csv``.
HABILIDADES_SCHEMA: tuple[str, ...] = (
    "id_logro",
    "nombre_logro",
    "descripcion_breve",
)
HERRAMIENTAS_SCHEMA: tuple[str, ...] = (
    "id_herramienta",
    "nombre_herramienta",
    "descripcion_breve_herramienta",
)
COBERTURA_SCHEMA: tuple[str, ...] = (
    "id_cob_curricular",
    "id_curso",
    "id_silabo",
    "id_competencia",
    "id_logro",
    "id_herramienta",
)

ARCHIVOS_SALIDA: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("curso.csv", CURSOS_SCHEMA),
    ("silabo.csv", SILABO_SCHEMA),
    ("catalogo_competencias.csv", COMPETENCIAS_SCHEMA),
    ("catalogo_logros.csv", HABILIDADES_SCHEMA),
    ("catalogo_herramientas.csv", HERRAMIENTAS_SCHEMA),
    ("cobertura_curricular.csv", COBERTURA_SCHEMA),
)

_ARCHIVOS_CURRICULARES_FINALES: frozenset[str] = frozenset(
    f"salidas/{nombre}" for nombre, _ in ARCHIVOS_SALIDA
)
_REPORTES_CURRICULARES_PRE_HITL: frozenset[str] = frozenset(
    {"release_gate.json", "extraccion_cactus.json"}
)


def _hitl_curricular_completado(release_gate: object) -> bool:
    """Determina si el paquete curricular ya puede exponerse como salida final."""

    if not isinstance(release_gate, dict) or release_gate.get("decision") != "ALLOW_IMPORT":
        return False
    checks = release_gate.get("checks")
    if not isinstance(checks, dict):
        return False
    aprobacion = checks.get("approval")
    return (
        isinstance(aprobacion, dict)
        and aprobacion.get("canonical_materialized") is True
        and aprobacion.get("pending_decision") == 0
    )


def _filtrar_outputs_curriculares(
    outputs: list[dict[str, object]],
    *,
    hitl_completado: bool,
) -> list[dict[str, object]]:
    """Expone únicamente los artefactos curriculares finales tras HITL."""

    publicos: list[dict[str, object]] = []
    for output in outputs:
        archivo = output.get("archivo")
        if not isinstance(archivo, str):
            continue
        if archivo not in _ARCHIVOS_CURRICULARES_FINALES or not hitl_completado:
            continue
        publicos.append(output)
    return publicos


def _filtrar_estado_publico(datos: dict[str, object]) -> dict[str, object]:
    """Aplica el contrato HITL también a manifests recuperados tras un reinicio."""

    if datos.get("tipo") != "silabos":
        return datos
    estado = dict(datos)
    release_gate = estado.get("release_gate")
    if not isinstance(release_gate, dict):
        limpieza = estado.get("limpieza_silabos")
        if isinstance(limpieza, dict):
            release_gate = limpieza.get("release_gate")
    hitl_completado = _hitl_curricular_completado(release_gate)
    outputs = estado.get("outputs")
    if isinstance(outputs, list):
        estado["outputs"] = _filtrar_outputs_curriculares(
            [dict(output) for output in outputs if isinstance(output, dict)],
            hitl_completado=hitl_completado,
        )
    limpieza = estado.get("limpieza_silabos")
    if isinstance(limpieza, dict):
        limpieza_publica = dict(limpieza)
        outputs_limpieza = limpieza_publica.get("outputs")
        if isinstance(outputs_limpieza, list):
            limpieza_publica["outputs"] = _filtrar_outputs_curriculares(
                [dict(output) for output in outputs_limpieza if isinstance(output, dict)],
                hitl_completado=hitl_completado,
            )
        estado["limpieza_silabos"] = limpieza_publica
    return estado


def validar_salidas_curriculares(
    salida: Path,
    registros: list[dict[str, object]],
    filas_por_archivo: dict[str, list[dict[str, str]]],
    competencias_fuente: dict[str, dict[str, object]],
    habilidades_fuente: dict[str, dict[str, object]],
    herramientas_fuente: dict[str, dict[str, object]],
    relaciones_canonicas: set[tuple[str, str, str, str, str]],
) -> tuple[Hallazgo, ...]:
    """Actúa como juez determinista antes de publicar los CSV canónicos."""

    hallazgos: list[Hallazgo] = []
    esquemas = {
        "curso.csv": CURSOS_SCHEMA,
        "silabo.csv": SILABO_SCHEMA,
        "catalogo_competencias.csv": COMPETENCIAS_SCHEMA,
        "catalogo_logros.csv": HABILIDADES_SCHEMA,
        "catalogo_herramientas.csv": HERRAMIENTAS_SCHEMA,
        "cobertura_curricular.csv": COBERTURA_SCHEMA,
    }
    filas_leidas: dict[str, list[dict[str, str]]] = {}
    for nombre, columnas in esquemas.items():
        ruta = salida / nombre
        if not ruta.is_file():
            hallazgos.append(
                Hallazgo(
                    codigo="CSV_SALIDA_AUSENTE",
                    severidad="error",
                    mensaje="Falta un CSV curricular requerido.",
                    hoja=nombre,
                )
            )
            continue
        with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
            lector = csv.DictReader(archivo)
            encabezado = tuple(lector.fieldnames or ())
            if encabezado != columnas:
                hallazgos.append(
                    Hallazgo(
                        codigo="CSV_ESQUEMA_INVALIDO",
                        severidad="error",
                        mensaje="El CSV no conserva exactamente el esquema del catálogo.",
                        hoja=nombre,
                        detalle=f"esperado={columnas}; recibido={encabezado}",
                    )
                )
            filas_leidas[nombre] = list(lector)

    cursos_csv = filas_leidas.get("curso.csv", [])
    competencias_csv = filas_leidas.get("catalogo_competencias.csv", [])
    logros_csv = filas_leidas.get("catalogo_logros.csv", [])
    herramientas_csv = filas_leidas.get("catalogo_herramientas.csv", [])
    cobertura_csv = filas_leidas.get("cobertura_curricular.csv", [])
    ids_competencias = _ids_unicos(
        competencias_csv,
        "id_competencia",
        "COMPETENCIA_ID_DUPLICADO",
        hallazgos,
    )
    ids_logros = _ids_unicos(
        logros_csv,
        "id_logro",
        "LOGRO_ID_DUPLICADO",
        hallazgos,
    )
    ids_herramientas = _ids_unicos(
        herramientas_csv,
        "id_herramienta",
        "HERRAMIENTA_ID_DUPLICADO",
        hallazgos,
    )
    ids_cursos = _ids_unicos(
        cursos_csv,
        "id_curso",
        "CURSO_ID_DUPLICADO",
        hallazgos,
    )
    for fila in cursos_csv:
        if not _texto(fila.get("id_carrera")):
            hallazgos.append(
                Hallazgo(
                    codigo="CURSO_CARRERA_AUSENTE",
                    severidad="error",
                    mensaje="El curso no puede publicarse sin una carrera autoritativa.",
                    hoja="curso.csv",
                    campo="id_carrera",
                )
            )
    _ids_unicos(
        cobertura_csv,
        "id_cob_curricular",
        "COBERTURA_ID_DUPLICADO",
        hallazgos,
    )

    for fila in competencias_csv:
        nombre = _texto(fila.get("nombre_competencia"))
        if nombre.lower().startswith("competencia referenciada por el sílabo"):
            hallazgos.append(
                Hallazgo(
                    codigo="COMPETENCIA_PLACEHOLDER_PUBLICADA",
                    severidad="error",
                    mensaje="El catálogo no puede publicar competencias placeholder.",
                    hoja="catalogo_competencias.csv",
                    detalle=nombre,
                )
            )

    ids_habilidad_fuente = set(habilidades_fuente)
    for fila in cobertura_csv:
        if _texto(fila.get("id_curso")) not in ids_cursos:
            hallazgos.append(
                Hallazgo(
                    codigo="COBERTURA_CURSO_INEXISTENTE",
                    severidad="error",
                    mensaje="La cobertura apunta a un curso que no existe en curso.csv.",
                    hoja="cobertura_curricular.csv",
                    campo="id_curso",
                    detalle=_texto(fila.get("id_curso")),
                )
            )
        for columna in ("id_curso", "id_silabo"):
            if not _texto(fila.get(columna)):
                hallazgos.append(
                    Hallazgo(
                        codigo="COBERTURA_IDENTIDAD_AUSENTE",
                        severidad="error",
                        mensaje="La cobertura debe conservar el curso y sílabo de origen.",
                        hoja="cobertura_curricular.csv",
                        campo=columna,
                    )
                )
        competencia_id = _texto(fila.get("id_competencia"))
        logro_id = _texto(fila.get("id_logro"))
        herramienta_id = _texto(fila.get("id_herramienta"))
        if competencia_id not in ids_competencias:
            hallazgos.append(
                Hallazgo(
                    codigo="COBERTURA_COMPETENCIA_INEXISTENTE",
                    severidad="error",
                    mensaje="La cobertura apunta a una competencia que no existe en el CSV.",
                    hoja="cobertura_curricular.csv",
                    detalle=competencia_id,
                )
            )
        if logro_id and logro_id not in ids_logros:
            hallazgos.append(
                Hallazgo(
                    codigo="COBERTURA_LOGRO_INEXISTENTE",
                    severidad="error",
                    mensaje="La cobertura apunta a un logro que no existe en el CSV.",
                    hoja="cobertura_curricular.csv",
                    detalle=logro_id,
                )
            )
        if herramienta_id and herramienta_id not in ids_herramientas:
            hallazgos.append(
                Hallazgo(
                    codigo="COBERTURA_HERRAMIENTA_INEXISTENTE",
                    severidad="error",
                    mensaje="La cobertura apunta a una herramienta que no existe en el CSV.",
                    hoja="cobertura_curricular.csv",
                    detalle=herramienta_id,
                )
            )

    ids_cobertura_canonica = {
        (id_curso, id_silabo, id_competencia, id_logro, id_herramienta)
        for (
            id_curso,
            id_silabo,
            id_competencia,
            id_logro,
            id_herramienta,
        ) in relaciones_canonicas
    }
    csv_cobertura = {
        (
            _texto(fila.get("id_curso")),
            _texto(fila.get("id_silabo")),
            _texto(fila.get("id_competencia")),
            _texto(fila.get("id_logro")),
            _texto(fila.get("id_herramienta")),
        )
        for fila in cobertura_csv
    }
    if not csv_cobertura.issubset(ids_cobertura_canonica):
        hallazgos.append(
            Hallazgo(
                codigo="COBERTURA_NO_CANONICA",
                severidad="error",
                mensaje="La cobertura CSV contiene relaciones que no pasaron el flujo canónico.",
                hoja="cobertura_curricular.csv",
            )
        )
    hallazgos.extend(validar_integridad_chh(filas_leidas, ids_cobertura_canonica))

    declaraciones = _declaraciones_de_registros(registros)
    nombres_declarados = {clave_concepto(declaracion["nombre"]) for declaracion in declaraciones}
    nombres_publicados = {
        clave_concepto(fila.get("nombre_competencia", "")) for fila in competencias_csv
    }
    if not nombres_declarados.issubset(nombres_publicados):
        faltantes = sorted(nombres_declarados - nombres_publicados)
        hallazgos.append(
            Hallazgo(
                codigo="COMPETENCIA_FUENTE_PERDIDA",
                severidad="error",
                mensaje="Una competencia declarada por el sílabo no llegó al catálogo.",
                hoja="catalogo_competencias.csv",
                detalle="; ".join(faltantes),
            )
        )

    if not (salida / "reportes" / "competencias_fuente.jsonl").is_file() or (
        not competencias_fuente and declaraciones
    ):
        hallazgos.append(
            Hallazgo(
                codigo="COMPETENCIA_FUENTE_NO_AUDITADA",
                severidad="error",
                mensaje="No se generó el reporte de competencias fuente.",
                hoja="reportes/competencias_fuente.jsonl",
            )
        )
    if not (salida / "reportes" / "habilidades_fuente.jsonl").is_file() or (
        not ids_habilidad_fuente and any(_logros(datos) for datos in _datos_registros(registros))
    ):
        hallazgos.append(
            Hallazgo(
                codigo="HABILIDAD_FUENTE_NO_AUDITADA",
                severidad="error",
                mensaje="No se generó el reporte de habilidades fuente.",
                hoja="reportes/habilidades_fuente.jsonl",
            )
        )
    ids_competencias_salida = {_texto(fila.get("id_competencia")) for fila in competencias_csv}
    ids_competencias_fuente = {
        _texto(fila.get("id_competencia_canonica"))
        for fila in competencias_fuente.values()
        if _texto(fila.get("id_competencia_canonica"))
    }
    ids_competencias_sin_proveniencia = ids_competencias_salida - ids_competencias_fuente
    if ids_competencias_sin_proveniencia:
        hallazgos.append(
            Hallazgo(
                codigo="COMPETENCIA_CANONICA_SIN_PROVENANCE",
                severidad="warning",
                mensaje=(
                    "Una competencia canónica no tiene una fila de provenance "
                    "que explique su origen curricular."
                ),
                hoja="reportes/competencias_fuente.jsonl",
                detalle="; ".join(sorted(ids_competencias_sin_proveniencia)),
            )
        )

    ids_logros_salida = {_texto(fila.get("id_logro")) for fila in logros_csv}
    ids_logros_fuente = {
        _texto(fila.get("id_habilidad_canonica"))
        for fila in habilidades_fuente.values()
        if _texto(fila.get("id_habilidad_canonica"))
    }
    ids_logros_sin_proveniencia = ids_logros_salida - ids_logros_fuente
    if ids_logros_sin_proveniencia:
        hallazgos.append(
            Hallazgo(
                codigo="LOGRO_SIN_PROVENANCE",
                severidad="warning",
                mensaje=(
                    "Un logro publicada no tiene una fila de provenance "
                    "que explique su logro de origen."
                ),
                hoja="reportes/habilidades_fuente.jsonl",
                detalle="; ".join(sorted(ids_logros_sin_proveniencia)),
            )
        )

    ids_herramientas_salida = {_texto(fila.get("id_herramienta")) for fila in herramientas_csv}
    ids_herramientas_fuente = {
        _texto(fila.get("id_herramienta_canonica"))
        for fila in herramientas_fuente.values()
        if _texto(fila.get("id_herramienta_canonica"))
    }
    ids_herramientas_sin_proveniencia = ids_herramientas_salida - ids_herramientas_fuente
    if ids_herramientas_sin_proveniencia:
        hallazgos.append(
            Hallazgo(
                codigo="HERRAMIENTA_CANONICA_SIN_PROVENANCE",
                severidad="warning",
                mensaje=(
                    "Una herramienta canónica no tiene una fila de provenance "
                    "que explique su evidencia estructurada."
                ),
                hoja="reportes/herramientas_fuente.jsonl",
                detalle="; ".join(sorted(ids_herramientas_sin_proveniencia)),
            )
        )
    return tuple(hallazgos)


def _conteo_logros_con_descripcion(registros: list[dict[str, object]]) -> int:
    return sum(
        1
        for datos in _datos_registros(registros)
        for logro in _logros(datos)
        if _texto(logro.get("descripcion"))
    )


def _ids_unicos(
    filas: list[dict[str, str]],
    columna: str,
    codigo: str,
    hallazgos: list[Hallazgo],
) -> set[str]:
    ids: set[str] = set()
    for fila in filas:
        identificador = _texto(fila.get(columna))
        if not identificador:
            hallazgos.append(
                Hallazgo(
                    codigo="CSV_ID_AUSENTE",
                    severidad="error",
                    mensaje="Una fila de catálogo no tiene identificador.",
                    campo=columna,
                )
            )
        elif identificador in ids:
            hallazgos.append(
                Hallazgo(
                    codigo=codigo,
                    severidad="error",
                    mensaje="Un identificador aparece más de una vez en el CSV.",
                    campo=columna,
                    detalle=identificador,
                )
            )
        ids.add(identificador)
    return ids


def _datos_registros(registros: list[dict[str, object]]) -> list[dict[str, object]]:
    return [datos for registro in registros if isinstance((datos := registro.get("datos")), dict)]
