"""Promotion, evidence relation, and discard mutations for curricular approvals."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, cast

from agente.normalizador.empleabilidad.catalogo import clave_concepto
from agente.normalizador.silabos import persistencia_aprobaciones as _persistencia
from agente.normalizador.silabos import validacion_aprobaciones as _validacion
from agente.normalizador.silabos.paquetes import identidad_fuente_chh
from agente.normalizador.silabos.politica_curricular import (
    MOTIVO_COMPETENCIA_GENERICA,
    es_competencia_generica,
)


def _promover(
    fila: dict[str, object],
    propuesta: dict[str, object],
    manifest: dict[str, object],
    archivos: dict[str, list[dict[str, str]]],
    fuentes: dict[str, list[dict[str, object]]],
    relaciones: list[dict[str, object]],
) -> str:
    try:
        identidad = identidad_fuente_chh(fila)
    except ValueError as exc:
        raise _validacion.DecisionCurricularInvalida(str(exc)) from exc
    tipo = _persistencia._texto(fila.get("tipo")).lower()
    nombre = _persistencia._texto(propuesta.get("nombre") or propuesta.get("id"))
    if tipo == "competencia" and es_competencia_generica(nombre):
        raise _validacion.DecisionCurricularInvalida(
            f"{MOTIVO_COMPETENCIA_GENERICA}: la competencia transversal no puede promoverse."
        )
    descripcion = _persistencia._texto(propuesta.get("descripcion")) or (
        f"Concepto curricular: {nombre}."
    )
    parametros = manifest.get("parametros")
    parametros = parametros if isinstance(parametros, dict) else {}
    carrera = _persistencia._texto(parametros.get("carrera"))
    periodo = _persistencia._texto(parametros.get("periodo"))
    id_canonico = _persistencia._id_canonico(tipo, carrera, periodo, nombre)
    if tipo == "competencia":
        id_canonico = _upsert(
            archivos["catalogo_competencias.csv"],
            "nombre_competencia",
            {
                "id_competencia": id_canonico,
                "nombre_competencia": nombre,
                "descripcion_breve_competencia": descripcion,
                "tipo_competencia": _persistencia._texto(propuesta.get("tipo")) or "dura",
            },
        )
        _upsert_fuente(
            fuentes["competencias_fuente.jsonl"],
            "id_competencia_fuente",
            {
                **identidad,
                "id_competencia_fuente": _persistencia._id_canonico(
                    "COMP_SRC", carrera, periodo, str(fila.get("id_pendiente"))
                ),
                "archivo": _persistencia._texto(fila.get("archivo")),
                "nombre_competencia_fuente": nombre,
                "descripcion_fuente": _persistencia._texto(fila.get("descripcion_fuente"))
                or descripcion,
                "id_competencia_canonica": id_canonico,
                "estado_resolucion": "ACEPTADA_POR_USUARIO",
                "metodo_resolucion": "APROBACION_EJECUTOR",
                "evidencia_fuente": _evidencia(fila),
            },
        )
    elif tipo == "habilidad":
        id_canonico = _upsert(
            archivos["catalogo_habilidades.csv"],
            "nombre_habilidad",
            {
                "id_habilidad": id_canonico,
                "nombre_habilidad": nombre,
                "descripcion_breve": descripcion,
            },
        )
        _upsert_fuente(
            fuentes["habilidades_fuente.jsonl"],
            "id_habilidad_fuente",
            {
                **identidad,
                "id_habilidad_fuente": identidad["id_habilidad_fuente"],
                "archivo": _persistencia._texto(fila.get("archivo")),
                "descripcion_fuente": _persistencia._texto(fila.get("descripcion_fuente"))
                or descripcion,
                "id_habilidad_canonica": id_canonico,
                "estado_resolucion": "ACEPTADA_POR_USUARIO",
                "metodo_resolucion": "APROBACION_EJECUTOR",
                "evidencia_fuente": _evidencia(fila),
            },
        )
    elif tipo == "herramienta":
        provenance = fila.get("evidencia_provenance")
        provenance = provenance if isinstance(provenance, Mapping) else {}
        origen = _persistencia._texto(provenance.get("origen"))
        seccion = _persistencia._texto(provenance.get("seccion"))
        texto_evidencia = _persistencia._texto(provenance.get("texto"))
        fuente_id = _persistencia._id_canonico(
            "HERR_SRC", carrera, periodo, str(fila.get("id_pendiente")), origen, texto_evidencia
        )
        fuente_id = _persistencia._texto(fila.get("id_herramienta_fuente")) or fuente_id
        id_canonico = _upsert(
            archivos["catalogo_herramientas.csv"],
            "nombre_herramienta",
            {
                "id_herramienta": id_canonico,
                "nombre_herramienta": nombre,
                "descripcion_breve_herramienta": descripcion,
            },
        )
        _upsert_fuente(
            fuentes["herramientas_fuente.jsonl"],
            "id_herramienta_fuente",
            {
                **identidad,
                "id_herramienta_fuente": fuente_id,
                "id_herramienta_canonica": id_canonico,
                "nombre_herramienta": nombre,
                "origen_fuente": origen or "APROBACION_EJECUTOR",
                "seccion_fuente": seccion or "APROBACION_EJECUTOR",
                "texto_evidencia": texto_evidencia or "; ".join(str(x) for x in _evidencia(fila)),
                "coincidencia": "LITERAL_PROGRAMA_ANALITICO"
                if origen == "programa_analitico"
                else "APROBACION_EJECUTOR",
                "estado_resolucion": "ACEPTADA_POR_USUARIO",
            },
        )
    else:
        raise _validacion.DecisionCurricularInvalida(f"Tipo curricular no soportado: {tipo!r}.")
    _añadir_relaciones_de_evidencia(fila, tipo, id_canonico, archivos, fuentes, relaciones)
    return id_canonico


def _añadir_relaciones_de_evidencia(
    fila: dict[str, object],
    tipo: str,
    id_canonico: str,
    archivos: dict[str, list[dict[str, str]]],
    fuentes: dict[str, list[dict[str, object]]],
    relaciones: list[dict[str, object]],
) -> None:
    try:
        identidad = identidad_fuente_chh(fila)
    except ValueError:
        return
    id_curso = identidad["id_curso"]
    id_silabo = identidad["id_silabo"]
    id_habilidad_fuente = identidad["id_habilidad_fuente"]
    id_relacion_fuente = _persistencia._texto(identidad.get("id_cob_curricular"))

    def pertenece_al_paquete(item: Mapping[str, object]) -> bool:
        return all(
            _persistencia._texto(item.get(key)) == identidad[key]
            for key in (
                "id_ejecucion",
                "carrera",
                "periodo",
                "id_curso",
                "id_silabo",
                "id_habilidad_fuente",
            )
        )

    relaciones_fuente = [
        relacion
        for relacion in fuentes.get("cobertura_curricular_fuente.jsonl", [])
        if _persistencia._texto(relacion.get("id_cob_curricular")) == id_relacion_fuente
    ]
    if id_relacion_fuente and len(relaciones_fuente) != 1:
        return
    if relaciones_fuente:
        relacion_fuente = relaciones_fuente[0]
        skill_id = (
            id_canonico
            if tipo == "habilidad"
            else _persistencia._texto(relacion_fuente.get("id_habilidad_canonica"))
        )
        comp_ids = [
            id_canonico
            if tipo == "competencia"
            else _persistencia._texto(relacion_fuente.get("id_competencia_canonica"))
        ]
        tool_ids = [
            id_canonico
            if tipo == "herramienta"
            else _persistencia._texto(relacion_fuente.get("id_herramienta_canonica"))
        ]
    else:
        habilidades = {
            _persistencia._texto(item.get("id_habilidad_fuente")): _persistencia._texto(
                item.get("id_habilidad_canonica")
            )
            for item in fuentes["habilidades_fuente.jsonl"]
            if pertenece_al_paquete(item)
        }
        skill_id = id_canonico if tipo == "habilidad" else habilidades.get(id_habilidad_fuente, "")
        comp_ids = [
            _persistencia._texto(item.get("id_competencia_canonica"))
            for item in fuentes["competencias_fuente.jsonl"]
            if pertenece_al_paquete(item)
            and _persistencia._texto(item.get("id_competencia_canonica"))
        ]
        if tipo == "competencia":
            comp_ids = [id_canonico]
        tool_ids = [
            _persistencia._texto(item.get("id_herramienta_canonica"))
            for item in fuentes["herramientas_fuente.jsonl"]
            if pertenece_al_paquete(item)
            and _persistencia._texto(item.get("id_herramienta_canonica"))
        ]
        if tipo == "herramienta":
            tool_ids = [id_canonico]

    if not skill_id:
        return
    valid_comp = {
        _persistencia._texto(row.get("id_competencia"))
        for row in archivos["catalogo_competencias.csv"]
    }
    valid_skill = {
        _persistencia._texto(row.get("id_habilidad"))
        for row in archivos["catalogo_habilidades.csv"]
    }
    valid_tool = {
        _persistencia._texto(row.get("id_herramienta"))
        for row in archivos["catalogo_herramientas.csv"]
    }
    for comp_id in dict.fromkeys(comp_ids):
        if comp_id not in valid_comp or skill_id not in valid_skill:
            continue
        herramientas_finales = [tool for tool in dict.fromkeys(tool_ids) if tool in valid_tool]
        if (
            not herramientas_finales
            and relaciones_fuente
            and _persistencia._texto(relaciones_fuente[0].get("id_herramienta_fuente"))
        ):
            continue
        if not herramientas_finales:
            herramientas_finales = [""]
        for tool_id in herramientas_finales:
            _upsert_relacion(
                relaciones,
                id_curso,
                id_silabo,
                comp_id,
                skill_id,
                tool_id,
                lineage=_persistencia._lineage_relacion(
                    fila, fuentes, identidad, comp_id, skill_id, tool_id
                ),
            )


def _upsert(filas: list[dict[str, str]], columna_nombre: str, fila: dict[str, str]) -> str:
    clave = clave_concepto(fila.get(columna_nombre, ""))
    for actual in filas:
        if clave_concepto(actual.get(columna_nombre, "")) == clave:
            return _persistencia._texto(
                actual.get(next(columna for columna in fila if columna.startswith("id_")))
            )
    filas.append(fila)
    return _persistencia._texto(
        next((valor for clave, valor in fila.items() if clave.startswith("id_")), "")
    )


def _upsert_fuente(
    filas: list[dict[str, object]], columna_id: str, fila: dict[str, object]
) -> None:
    identificador = _persistencia._texto(fila.get(columna_id))
    for indice, actual in enumerate(filas):
        if _persistencia._texto(actual.get(columna_id)) == identificador:
            fusionada = dict(actual)
            fusionada.update(
                {clave: valor for clave, valor in fila.items() if valor not in ("", None, [])}
            )
            filas[indice] = fusionada
            return
    filas.append(fila)


def _upsert_relacion(
    relaciones: list[dict[str, object]],
    id_curso: str,
    id_silabo: str,
    id_competencia: str,
    id_habilidad: str,
    id_herramienta: str,
    *,
    lineage: Mapping[str, object] | None = None,
) -> None:
    clave = (id_curso, id_silabo, id_competencia, id_habilidad, id_herramienta)
    if clave in {_persistencia._clave_relacion(row) for row in relaciones}:
        return
    nueva = cast(dict[str, object], _persistencia._fila_relacion(*clave))
    nueva.update(
        {clave: valor for clave, valor in (lineage or {}).items() if _persistencia._texto(valor)}
    )
    relaciones.append(nueva)


def _auditoria_descarte_paquete(
    package_id: str,
    filas: Sequence[Mapping[str, object]],
    manifest: Mapping[str, object],
    actor: str,
    decidido_en: str,
    reason: str,
) -> dict[str, object]:
    parametros = manifest.get("parametros")
    parametros = parametros if isinstance(parametros, Mapping) else {}
    identidad = next(
        (
            dict(_persistencia._mapping(fila.get("source_identity")))
            for fila in filas
            if _persistencia._mapping(fila.get("source_identity"))
        ),
        {},
    )
    evidencia = sorted(
        cast(Sequence[Any], {item for fila in filas for item in _evidencia(fila) if item})
    )
    propuestas = [
        {
            "tipo": _persistencia._texto(fila.get("tipo")),
            "nombre": _persistencia._texto(
                _persistencia._mapping(fila.get("propuesta")).get("nombre")
            ),
        }
        for fila in filas
    ]
    return {
        "version": "package-discard-audit/v1",
        "package_id": package_id,
        "source_identity": identidad,
        "carrera": _persistencia._clave_ruta(_persistencia._texto(parametros.get("carrera"))),
        "periodo": re.sub(r"[^0-9-]", "", _persistencia._texto(parametros.get("periodo"))),
        "decidido_en": decidido_en,
        "actor": actor,
        "reason": reason,
        "evidence": evidencia,
        "propuestas": propuestas,
    }


def _retirar_relaciones_descartadas(
    relaciones: list[dict[str, object]],
    fuentes: dict[str, list[dict[str, object]]],
    descartes: Sequence[Mapping[str, object]],
) -> None:
    if not descartes:
        return
    descartadas = {
        _persistencia._texto(
            _persistencia._mapping(descarte.get("source_identity")).get("id_cob_curricular")
        )
        for descarte in descartes
    }
    descartadas.discard("")
    fuente_relaciones = fuentes.get("cobertura_curricular_fuente.jsonl", [])
    for fuente in fuente_relaciones:
        if _persistencia._texto(fuente.get("id_cob_curricular")) in descartadas:
            fuente["estado_resolucion"] = "DESCARTADO_POR_USUARIO"
    activas = {
        (
            _persistencia._texto(fuente.get("id_competencia_canonica")),
            _persistencia._texto(fuente.get("id_habilidad_canonica")),
            _persistencia._texto(fuente.get("id_herramienta_canonica")),
        )
        for fuente in fuente_relaciones
        if _persistencia._texto(fuente.get("estado_resolucion")) != "DESCARTADO_POR_USUARIO"
    }
    relaciones[:] = [
        relacion
        for relacion in relaciones
        if (
            _persistencia._texto(relacion.get("id_competencia")),
            _persistencia._texto(relacion.get("id_habilidad")),
            _persistencia._texto(relacion.get("id_herramienta")),
        )
        in activas
        or not fuente_relaciones
    ]


def _evidencia(fila: Mapping[str, object]) -> list[object]:
    evidencia: Any = fila.get("evidencia")
    return list(evidencia) if isinstance(evidencia, list) else []
