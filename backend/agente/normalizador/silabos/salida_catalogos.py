"""Materialización del contrato curricular basado directamente en sílabos.

Este módulo mantiene la extracción determinista separada de la inferencia: los
registros de entrada vienen de los parsers DOCX/PDF y las competencias técnicas
son decisiones ya validadas del proveedor LLM configurado.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from agente.normalizador.modelos import Hallazgo
from agente.normalizador.silabos.extraccion_curricular import _hash_id

CURSOS_SCHEMA = (
    "id_curso",
    "nombre_curso",
    "coordinador",
    "creditos",
    "nivel",
    "tipo_curso",
    "codigo_curso",
    "id_carrera",
)
SILABOS_SCHEMA = (
    "id_silabo",
    "codigo_silabo",
    "sumilla",
    "id_curso",
    "periodo_academico",
)
COMPETENCIAS_SCHEMA = (
    "id_competencia",
    "nombre_competencia",
    "descripcion_breve_competencia",
    "tipo_competencia",
    "codigo_competencia",
)
LOGROS_SCHEMA = ("id_logro", "logro")
COBERTURA_SCHEMA = (
    "id_cob_curricular",
    "id_curso",
    "id_silabo",
    "id_competencia",
    "id_logro",
)
ARCHIVOS_CATALOGO = (
    ("curso.csv", CURSOS_SCHEMA),
    ("silabo.csv", SILABOS_SCHEMA),
    ("catalogo_competencias.csv", COMPETENCIAS_SCHEMA),
    ("catalogo_logros.csv", LOGROS_SCHEMA),
    ("cobertura_curricular.csv", COBERTURA_SCHEMA),
)


@dataclass(frozen=True, slots=True)
class ResultadoCatalogosTecnicos:
    """Resumen de la salida técnica CL independiente de la empleabilidad."""

    publicable: bool
    relaciones: int
    competencias: int
    pendientes: int
    outputs: tuple[dict[str, object], ...]
    release_gate: dict[str, object]
    hallazgos: tuple[Hallazgo, ...] = ()
    cuarentena: tuple[dict[str, object], ...] = ()


def _texto(valor: object) -> str:
    return " ".join(str(valor or "").split())


def _lista_mapeos(valor: object) -> list[Mapping[str, object]]:
    if not isinstance(valor, Sequence) or isinstance(valor, (str, bytes)):
        return []
    return [fila for fila in valor if isinstance(fila, Mapping)]


def _codigos(valor: object) -> list[str]:
    if not isinstance(valor, Sequence) or isinstance(valor, (str, bytes)):
        return []
    return [_texto(codigo).upper() for codigo in valor if _texto(codigo)]


def _agregar_unico(
    destino: dict[str, dict[str, str]],
    fila: dict[str, str],
    clave: str,
    *,
    variantes_canonicas: bool = False,
) -> None:
    identificador = fila[clave]
    anterior = destino.get(identificador)
    if anterior is not None and anterior != fila:
        if not variantes_canonicas:
            raise ValueError(f"Identidad curricular ambigua para {identificador}")
        destino[identificador] = min(
            (anterior, fila),
            key=lambda valor: tuple(valor[campo] for campo in sorted(valor)),
        )
        return
    destino[identificador] = fila


def _cobertura(
    id_curso: str,
    id_silabo: str,
    id_competencia: str,
    id_logro: str,
) -> dict[str, str]:
    return {
        "id_cob_curricular": _hash_id("COB_CUR", id_curso, id_silabo, id_competencia, id_logro),
        "id_curso": id_curso,
        "id_silabo": id_silabo,
        "id_competencia": id_competencia,
        "id_logro": id_logro,
    }


def _escribir_csv(ruta: Path, columnas: tuple[str, ...], filas: Iterable[dict[str, str]]) -> None:
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(filas)


def _output_metadata(
    ruta: Path,
    base: Path,
    tipo: str,
    registros: int,
) -> dict[str, object]:
    digest = hashlib.sha256(ruta.read_bytes()).hexdigest()
    return {
        "tipo": tipo,
        "archivo": ruta.relative_to(base).as_posix(),
        "registros": registros,
        "bytes": ruta.stat().st_size,
        "sha256": digest,
    }


def construir_salidas_tecnicas(
    registros: Sequence[Mapping[str, object]],
    salida: Path,
    *,
    carrera: str,
    periodo_academico: str,
    propuestas_tecnicas: Sequence[Mapping[str, object]] = (),
    propuestas_aprobadas: Sequence[Mapping[str, object]] = (),
    analisis_tecnico: Mapping[str, object] | None = None,
) -> ResultadoCatalogosTecnicos:
    """Build the technical package from extracted records and approved proposals only."""

    resumen = construir_catalogos_curriculares(
        registros,
        salida,
        carrera=carrera,
        periodo_academico=periodo_academico,
        competencias_tecnicas=[
            {**dict(propuesta), "estado_aprobacion": "APROBADA"}
            for propuesta in propuestas_aprobadas
        ],
    )
    hallazgos = tuple(
        hallazgo
        for hallazgo in cast(Sequence[object], resumen.get("hallazgos", ()))
        if isinstance(hallazgo, Hallazgo)
    )
    cuarentena = tuple(
        dict(fila)
        for fila in cast(Sequence[object], resumen.get("cuarentena", ()))
        if isinstance(fila, Mapping)
    )
    archivos_resumen = resumen.get("archivos")
    if not isinstance(archivos_resumen, Mapping):
        raise ValueError("La salida técnica no devolvió conteos de archivos")
    conteos: dict[str, int] = {}
    for nombre, _ in ARCHIVOS_CATALOGO:
        cantidad = archivos_resumen.get(nombre)
        if not isinstance(cantidad, int):
            raise ValueError(f"La salida técnica no devolvió el conteo de {nombre}")
        conteos[nombre] = cantidad
    reportes = salida / "reportes"
    reportes.mkdir(parents=True, exist_ok=True)
    archivos = {nombre: salida / nombre for nombre, _ in ARCHIVOS_CATALOGO}
    archivos_ok = all(ruta.is_file() for ruta in archivos.values())
    estado_analisis = "COMPLETADO"
    advertencias_analisis: Sequence[object] = ()
    if analisis_tecnico is not None:
        estado_analisis = _texto(analisis_tecnico.get("estado")) or "DESCONOCIDO"
        advertencias = analisis_tecnico.get("advertencias")
        if isinstance(advertencias, Sequence) and not isinstance(advertencias, (str, bytes)):
            advertencias_analisis = advertencias
    analisis_completo = estado_analisis == "COMPLETADO" and not advertencias_analisis
    pendientes = len(propuestas_tecnicas)
    blockers: list[str] = []
    if not archivos_ok:
        blockers.append("DETERMINISTIC_OUTPUT_INCOMPLETE")
    if not analisis_completo:
        blockers.append(
            "TECHNICAL_ANALYSIS_INCOMPLETE"
            if estado_analisis == "COMPLETADO_CON_ADVERTENCIAS" or advertencias_analisis
            else "TECHNICAL_ANALYSIS_FAILED"
        )
    if pendientes:
        blockers.append("PENDING_TECHNICAL_APPROVAL")
    if cuarentena:
        blockers.append("UNLINKED_SOURCE_OUTCOME")
    gate: dict[str, object] = {
        "version": "curricular-release-gate/v1",
        "decision": "ALLOW_IMPORT" if not blockers else "BLOCK_IMPORT",
        "carrera": _texto(carrera).upper(),
        "periodo": _texto(periodo_academico),
        "blockers": blockers,
        "checks": {
            "deterministic_outputs": {
                "ok": archivos_ok,
                "files": [nombre for nombre, _ in ARCHIVOS_CATALOGO],
            },
            "analysis": {
                "ok": analisis_completo,
                "state": estado_analisis,
                "warning_count": len(advertencias_analisis),
            },
            "approval": {
                "ok": pendientes == 0,
                "pending_count": pendientes,
                "message": (
                    f"{pendientes} technical proposals await approval."
                    if pendientes
                    else "No technical proposals await approval."
                ),
            },
            "source_outcomes": {
                "ok": not cuarentena,
                "quarantined_count": len(cuarentena),
                "message": (
                    f"{len(cuarentena)} source learning outcomes lack a resolvable "
                    "competency relation."
                    if cuarentena
                    else "All source learning outcomes have a competency relation."
                ),
            },
        },
        "observability": {
            "source_records": len(registros),
            "canonical_competencies": conteos["catalogo_competencias.csv"],
            "canonical_relations": conteos["cobertura_curricular.csv"],
            "pending_records": pendientes,
        },
    }
    ruta_gate = reportes / "release_gate.json"
    ruta_gate.write_text(
        json.dumps(gate, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    outputs = tuple(
        _output_metadata(
            archivos[nombre],
            salida.parent,
            "csv_curricular",
            conteos[nombre],
        )
        for nombre, _ in ARCHIVOS_CATALOGO
    ) + (_output_metadata(ruta_gate, salida.parent, "release_gate", 1),)
    return ResultadoCatalogosTecnicos(
        publicable=bool(registros) and not blockers,
        relaciones=conteos["cobertura_curricular.csv"],
        competencias=conteos["catalogo_competencias.csv"],
        pendientes=pendientes,
        outputs=outputs,
        release_gate=gate,
        hallazgos=hallazgos,
        cuarentena=cuarentena,
    )


def construir_catalogos_curriculares(
    registros: Sequence[Mapping[str, object]],
    salida: Path,
    *,
    carrera: str,
    periodo_academico: str,
    competencias_tecnicas: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Construye catálogos para un único lote carrera-periodo.

    ``competencias_tecnicas`` contiene únicamente propuestas aprobadas. Cada
    resultado debe referenciar ``id_silabo`` y ``logros`` (IDs o textos completos)
    para producir cobertura verificable; las propuestas pendientes no se materializan.
    """

    if not _texto(carrera) or not _texto(periodo_academico):
        raise ValueError("La carrera y el periodo académico son obligatorios")
    for registro in registros:
        if _texto(registro.get("carrera")).casefold() != _texto(carrera).casefold():
            raise ValueError("El lote mezcla carreras")
        if _texto(registro.get("periodo")) != _texto(periodo_academico):
            raise ValueError("El lote mezcla periodos académicos")

    cursos: dict[str, dict[str, str]] = {}
    silabos: dict[str, dict[str, str]] = {}
    competencias: dict[str, dict[str, str]] = {}
    logros: dict[str, dict[str, str]] = {}
    coberturas: dict[str, dict[str, str]] = {}
    hallazgos: list[Hallazgo] = []
    cuarentena: list[dict[str, object]] = []
    outcomes_sin_competencia: list[dict[str, object]] = []
    competencias_por_silabo_codigo: dict[tuple[str, str], str] = {}
    logros_por_silabo: dict[str, dict[str, str]] = {}
    id_carrera = _hash_id("CAR", carrera)

    for registro in registros:
        datos = registro.get("datos")
        if not isinstance(datos, Mapping):
            continue
        id_curso = _texto(registro.get("id_curso"))
        id_silabo = _texto(registro.get("id_silabo"))
        codigo_curso = _texto(datos.get("codigo_curso"))
        if not id_curso or not id_silabo:
            raise ValueError("Todo registro debe incluir id_curso e id_silabo")

        _agregar_unico(
            cursos,
            {
                "id_curso": id_curso,
                "nombre_curso": _texto(datos.get("nombre_curso") or datos.get("curso")),
                "coordinador": _texto(datos.get("coordinador")),
                "creditos": _texto(datos.get("creditos")),
                "nivel": _texto(datos.get("nivel") or datos.get("ciclo")),
                "tipo_curso": _texto(datos.get("tipo_curso")),
                "codigo_curso": codigo_curso,
                "id_carrera": id_carrera,
            },
            "id_curso",
        )
        _agregar_unico(
            silabos,
            {
                "id_silabo": id_silabo,
                "codigo_silabo": _texto(datos.get("codigo_silabo") or codigo_curso),
                "sumilla": _texto(datos.get("sumilla")),
                "id_curso": id_curso,
                "periodo_academico": periodo_academico,
            },
            "id_silabo",
        )

        for declarada in _lista_mapeos(datos.get("competencias_declaradas")):
            nombre = _texto(declarada.get("nombre"))
            descripcion = _texto(declarada.get("descripcion"))
            codigo = _texto(declarada.get("codigo")).upper()
            tipo = _texto(declarada.get("tipo"))
            if not nombre or not codigo or tipo not in {"generica", "especifica"}:
                continue
            id_competencia = _hash_id("COMP", tipo, codigo, nombre, descripcion)
            _agregar_unico(
                competencias,
                {
                    "id_competencia": id_competencia,
                    "nombre_competencia": nombre,
                    "descripcion_breve_competencia": descripcion,
                    "tipo_competencia": tipo,
                    "codigo_competencia": codigo,
                },
                "id_competencia",
                variantes_canonicas=True,
            )
            competencias_por_silabo_codigo[(id_silabo, codigo)] = id_competencia

        ids_competencias_silabo = sorted(
            {
                id_competencia
                for (silabo, _), id_competencia in competencias_por_silabo_codigo.items()
                if silabo == id_silabo
            }
        )
        logros_silabo: dict[str, str] = {}
        logro_general = _texto(datos.get("logro_general"))
        if logro_general:
            id_logro = _hash_id("LOGRO", id_silabo, logro_general)
            _agregar_unico(logros, {"id_logro": id_logro, "logro": logro_general}, "id_logro")
            logros_silabo[logro_general.casefold()] = id_logro
            if not ids_competencias_silabo:
                outcomes_sin_competencia.append(
                    {
                        "id_curso": id_curso,
                        "id_silabo": id_silabo,
                        "id_logro": id_logro,
                        "campo": "logro_general",
                        "tipo": "general",
                        "logro": logro_general,
                        "evidencia": {"logro_general": logro_general},
                    }
                )
            for id_competencia in ids_competencias_silabo:
                fila = _cobertura(id_curso, id_silabo, id_competencia, id_logro)
                coberturas[fila["id_cob_curricular"]] = fila

        for especifico in _lista_mapeos(datos.get("logros_especificos")):
            texto_logro = _texto(especifico.get("descripcion") or especifico.get("logro"))
            if not texto_logro:
                continue
            id_logro = _hash_id("LOGRO", id_silabo, texto_logro)
            _agregar_unico(logros, {"id_logro": id_logro, "logro": texto_logro}, "id_logro")
            logros_silabo[texto_logro.casefold()] = id_logro
            ids_competencia: set[str] = set()
            for codigo in _codigos(especifico.get("codigos_competencia")):
                id_exacto = competencias_por_silabo_codigo.get((id_silabo, codigo))
                if id_exacto:
                    ids_competencia.add(id_exacto)
                elif codigo in {"G", "E", "C"}:
                    ids_competencia.update(
                        id_competencia
                        for (silabo, codigo_declarado), id_competencia in (
                            competencias_por_silabo_codigo.items()
                        )
                        if silabo == id_silabo and codigo_declarado.startswith(codigo)
                    )
            if not ids_competencia:
                outcomes_sin_competencia.append(
                    {
                        "id_curso": id_curso,
                        "id_silabo": id_silabo,
                        "id_logro": id_logro,
                        "campo": "logros_especificos",
                        "tipo": "especifico",
                        "logro": texto_logro,
                        "evidencia": dict(especifico),
                    }
                )
            for id_competencia in sorted(ids_competencia):
                fila = _cobertura(id_curso, id_silabo, id_competencia, id_logro)
                coberturas[fila["id_cob_curricular"]] = fila
        logros_por_silabo[id_silabo] = logros_silabo

    inferencias: list[dict[str, object]] = []
    curso_por_silabo = {fila["id_silabo"]: fila["id_curso"] for fila in silabos.values()}
    contador_tecnico: dict[str, int] = {}
    for tecnica in competencias_tecnicas:
        if tecnica.get("estado_aprobacion") != "APROBADA":
            raise ValueError(
                "No se puede materializar una competencia técnica pendiente de aprobación"
            )
        id_silabo = _texto(tecnica.get("id_silabo"))
        id_curso = curso_por_silabo.get(id_silabo, "")
        nombre = _texto(tecnica.get("nombre_competencia") or tecnica.get("nombre"))
        descripcion = _texto(
            tecnica.get("descripcion_breve_competencia") or tecnica.get("descripcion")
        )
        if not id_curso or not nombre or not descripcion:
            raise ValueError("Una competencia técnica no referencia un sílabo válido")
        contador_tecnico[id_silabo] = contador_tecnico.get(id_silabo, 0) + 1
        codigo = _texto(tecnica.get("codigo_competencia")).upper() or (
            f"T{contador_tecnico[id_silabo]}"
        )
        if not codigo.startswith("T"):
            raise ValueError("Las competencias técnicas deben usar códigos T")
        id_competencia = _hash_id(
            "COMP",
            "tecnica",
            _texto(tecnica.get("catalogo_ref")) or nombre,
            nombre,
            descripcion,
        )
        _agregar_unico(
            competencias,
            {
                "id_competencia": id_competencia,
                "nombre_competencia": nombre,
                "descripcion_breve_competencia": descripcion,
                "tipo_competencia": "tecnica",
                "codigo_competencia": codigo,
            },
            "id_competencia",
            variantes_canonicas=True,
        )
        logros_disponibles = logros_por_silabo.get(id_silabo, {})
        ids_disponibles = set(logros_disponibles.values())
        referencias_logro: list[str] = []
        ids_referenciados = tecnica.get("id_logros")
        if isinstance(ids_referenciados, Sequence) and not isinstance(
            ids_referenciados, (str, bytes)
        ):
            for valor in ids_referenciados:
                referencia = _texto(valor)
                if not referencia:
                    continue
                if referencia in ids_disponibles:
                    referencias_logro.append(referencia)
                    continue
                referencia_texto = logros_disponibles.get(referencia.casefold())
                if referencia_texto is None:
                    raise ValueError(
                        f"La competencia técnica referencia un logro inexistente de {id_silabo}"
                    )
                referencias_logro.append(referencia_texto)
        logros_referenciados = tecnica.get("logros")
        if isinstance(logros_referenciados, Sequence) and not isinstance(
            logros_referenciados, (str, bytes)
        ):
            for logro in logros_referenciados:
                texto_logro = _texto(logro)
                if not texto_logro:
                    continue
                id_logro_resuelto = logros_disponibles.get(texto_logro.casefold())
                if id_logro_resuelto is None:
                    raise ValueError(
                        f"La competencia técnica referencia un logro inexistente de {id_silabo}"
                    )
                referencias_logro.append(id_logro_resuelto)
        ids_logro = list(dict.fromkeys(referencias_logro))
        if not ids_logro:
            raise ValueError(
                f"La competencia técnica aprobada debe referenciar un logro de {id_silabo}"
            )
        for id_logro in ids_logro:
            fila = _cobertura(id_curso, id_silabo, id_competencia, id_logro)
            coberturas[fila["id_cob_curricular"]] = fila
        inferencias.append(
            {
                **dict(tecnica),
                "id_curso": id_curso,
                "id_silabo": id_silabo,
                "id_competencia": id_competencia,
                "codigo_competencia": codigo,
                "tipo_competencia": "tecnica",
            }
        )

    ids_logros_cubiertos = {str(fila.get("id_logro") or "") for fila in coberturas.values()}
    for outcome in outcomes_sin_competencia:
        id_logro = str(outcome.get("id_logro") or "")
        if id_logro in ids_logros_cubiertos:
            continue
        hallazgo = Hallazgo(
            codigo="LOGRO_SIN_COMPETENCIA",
            severidad="warning",
            mensaje=("El logro fuente no tiene una competencia resoluble; queda en cuarentena."),
            campo=_texto(outcome.get("campo")),
            detalle=(f"{_texto(outcome.get('id_silabo'))}: {_texto(outcome.get('logro'))}"),
        )
        hallazgos.append(hallazgo)
        cuarentena.append(
            {
                "id_curso": outcome.get("id_curso"),
                "id_silabo": outcome.get("id_silabo"),
                "codigo": hallazgo.codigo,
                "tipo": outcome.get("tipo"),
                "logro": outcome.get("logro"),
                "evidencia": outcome.get("evidencia"),
            }
        )

    salida.mkdir(parents=True, exist_ok=True)
    filas_por_archivo = {
        "curso.csv": list(cursos.values()),
        "silabo.csv": list(silabos.values()),
        "catalogo_competencias.csv": list(competencias.values()),
        "catalogo_logros.csv": list(logros.values()),
        "cobertura_curricular.csv": list(coberturas.values()),
    }
    for nombre, columnas in ARCHIVOS_CATALOGO:
        filas = sorted(
            filas_por_archivo[nombre],
            key=lambda fila: tuple(fila.get(columna, "") for columna in columnas),
        )
        _escribir_csv(salida / nombre, columnas, filas)
    ruta_inferencias = salida / "inferencias_tecnicas.jsonl"
    with ruta_inferencias.open("w", encoding="utf-8", newline="\n") as archivo:
        for inferencia in inferencias:
            archivo.write(json.dumps(inferencia, ensure_ascii=False, separators=(",", ":")) + "\n")

    return {
        "archivos": {nombre: len(filas_por_archivo[nombre]) for nombre, _ in ARCHIVOS_CATALOGO},
        "inferencias_tecnicas": len(inferencias),
        "carrera": carrera,
        "periodo_academico": periodo_academico,
        "hallazgos": tuple(hallazgos),
        "cuarentena": tuple(cuarentena),
    }
