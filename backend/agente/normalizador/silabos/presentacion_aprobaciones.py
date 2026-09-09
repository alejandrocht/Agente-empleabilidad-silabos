"""HTTP DTO projections for curricular approval presentation."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from agente.normalizador.silabos.paquetes import (
    IDENTITY_FIELDS,
    PACKAGE_ID_FIELD,
    RELATION_KEYS,
)


def filas_para_presentacion_api(filas: Sequence[object]) -> list[object]:
    """Project pending rows to the compact fields rendered by the approval UI."""

    return [
        _fila_para_presentacion_api(fila) if isinstance(fila, Mapping) else fila for fila in filas
    ]


def paquetes_para_presentacion_api(
    paquetes: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Project complete CHH packages into the HTTP-only approval presentation DTO.

    Full packages remain the source for revisions, decisions, validation, and
    persisted artifacts. This projection intentionally removes duplicated and
    deep provenance that the approval panel never renders.
    """

    return [_paquete_para_presentacion_api(paquete) for paquete in paquetes]


def _paquete_para_presentacion_api(paquete: Mapping[str, object]) -> dict[str, object]:
    identidad = _identidad_para_presentacion_api(paquete.get("source_identity"))
    componentes_origen = paquete.get("componentes")
    componentes_origen = componentes_origen if isinstance(componentes_origen, Mapping) else {}
    componentes = {
        nombre: [
            _componente_para_presentacion_api(componente)
            for componente in _lista_mapeos_para_presentacion_api(
                componentes_origen.get(nombre) or paquete.get(nombre)
            )
        ]
        for nombre in ("competencias", "habilidades", "herramientas")
    }
    filas = filas_para_presentacion_api(_lista_para_presentacion_api(paquete.get("filas")))
    relaciones = [
        _relacion_para_presentacion_api(relacion)
        for relacion in _lista_mapeos_para_presentacion_api(paquete.get("relaciones"))
    ]
    relaciones_canonicas = [
        _triple_canonico_para_presentacion_api(triple)
        for triple in _lista_mapeos_para_presentacion_api(paquete.get("relaciones_canonicas"))
    ]
    propuestas_pendientes = [
        _propuesta_pendiente_para_presentacion_api(propuesta)
        for propuesta in _lista_mapeos_para_presentacion_api(paquete.get("propuestas_pendientes"))
    ]
    evidencia_fuente = paquete.get("source_evidence")
    evidencia_fuente = evidencia_fuente if isinstance(evidencia_fuente, Mapping) else {}
    source_relationships = [
        _relacion_para_presentacion_api(relacion)
        for relacion in _lista_mapeos_para_presentacion_api(
            evidencia_fuente.get("relationships") or paquete.get("source_relationships")
        )
    ]
    aliases = [
        _alias_para_presentacion_api(alias)
        for alias in _lista_mapeos_para_presentacion_api(paquete.get("aliases"))
    ]
    resultado = _campos_para_presentacion_api(
        paquete,
        (
            PACKAGE_ID_FIELD,
            "package_id",
            "package_source_key",
            "clave_paquete_chh",
            "decision",
            "package_decision",
            "requires_human_decision",
            "requiere_decision",
            "decision_state",
            "estado_decision",
            "decision_visible",
            "resumen_decision",
        ),
    )
    resultado["source_identity"] = identidad
    for alias, campo in (
        ("execution_id", "id_ejecucion"),
        ("career", "carrera"),
        ("period", "periodo"),
    ):
        valor = paquete.get(alias, identidad.get(campo))
        if _texto(valor):
            resultado[alias] = _texto(valor)
    for campo in ("id_curso", "id_silabo"):
        valor = paquete.get(campo, identidad.get(campo))
        if _texto(valor):
            resultado[campo] = _texto(valor)
    resultado["componentes"] = componentes
    resultado["relaciones_canonicas"] = relaciones_canonicas
    resultado["propuestas_pendientes"] = propuestas_pendientes
    resultado["competency_blockers"] = _lista_mapeos_para_presentacion_api(
        paquete.get("competency_blockers")
    )
    resultado["source_evidence"] = {
        "relationships": source_relationships,
        "rows": filas,
    }
    resultado["filas"] = filas
    resultado["relaciones"] = relaciones
    resultado["aliases"] = aliases
    for campo in ("id_pendientes", "manual_review_rows", "alias_ids", "flags"):
        if campo in paquete:
            resultado[campo] = _textos_para_presentacion_api(paquete.get(campo))
    if "pendientes" in paquete:
        resultado["pendientes"] = _pendientes_para_presentacion_api(paquete.get("pendientes"))
    resultado["totales"] = {
        "filas": len(filas),
        "relaciones": len(relaciones),
        "aliases": len(aliases),
        "componentes": {nombre: len(valores) for nombre, valores in componentes.items()},
    }
    return resultado


def _triple_canonico_para_presentacion_api(triple: Mapping[str, object]) -> dict[str, object]:
    """Keep canonical triples explicit and compact for the approval UI."""

    resultado: dict[str, object] = {}
    for tipo in ("competencia", "habilidad", "herramienta"):
        referencia = triple.get(tipo)
        if isinstance(referencia, Mapping):
            resultado[tipo] = _campos_para_presentacion_api(referencia, ("id", "nombre"))
        elif _texto(referencia):
            resultado[tipo] = {"nombre": _texto(referencia)}
    return resultado


def _propuesta_pendiente_para_presentacion_api(
    propuesta: Mapping[str, object],
) -> dict[str, object]:
    resultado = _campos_para_presentacion_api(
        propuesta,
        ("tipo", "nombre", "descripcion", "id_pendiente"),
    )
    if "evidencia" in propuesta:
        resultado["evidencia"] = _textos_para_presentacion_api(propuesta.get("evidencia"))
    if "source_identity" in propuesta:
        resultado["source_identity"] = _identidad_para_presentacion_api(
            propuesta.get("source_identity")
        )
    return resultado


def _fila_para_presentacion_api(fila: Mapping[str, object]) -> dict[str, object]:
    resultado = _campos_para_presentacion_api(
        fila,
        (
            "id_pendiente",
            "tipo",
            "estado_resolucion",
            "decision",
            "requiere_decision",
            "archivo",
            "id_ejecucion",
            "execution_id",
            "carrera",
            "career",
            "periodo",
            "period",
            "id_curso",
            "id_silabo",
            "id_logro",
            "id_habilidad_fuente",
            "id_competencia_fuente",
            "id_herramienta_fuente",
            "id_canonico",
            "id_canonico_propuesto",
            "id_competencia",
            "id_habilidad",
            "id_herramienta",
            "nombre_catalogo",
            "nombre_canonico",
            "nombre_propuesto",
            "nombre_competencia_fuente",
            "nombre_habilidad_fuente",
            "nombre_herramienta_fuente",
            "nombre_fuente",
            "descripcion_fuente",
            "relevancia_herramienta",
            "tool_relevance",
            "canonical",
            "auto_deduplicated",
            "auto_deduplication_state",
            "exact_duplicate_representative_id",
            "representative_id",
            "auto_dedup_representative_id",
            "grupo_duplicado_exacto",
            "exact_duplicate_group",
            "grupo_duplicado_semantico",
            "semantic_duplicate_group",
            "duplicado_exacto",
            "exact_duplicate",
            "posible_duplicado_semantico",
            "semantic_duplicate",
            "herramienta_no_relacionada",
            "suspicious_tool",
        ),
    )
    propuesta = fila.get("propuesta")
    if isinstance(propuesta, Mapping):
        resultado["propuesta"] = _campos_para_presentacion_api(
            propuesta, ("id", "nombre", "descripcion", "tipo")
        )
    if "evidencia" in fila:
        resultado["evidencia"] = _textos_para_presentacion_api(fila.get("evidencia"))
    if "flags" in fila:
        resultado["flags"] = _textos_para_presentacion_api(fila.get("flags"))
    if "source_identity" in fila:
        resultado["source_identity"] = _identidad_para_presentacion_api(fila.get("source_identity"))
    return resultado


def _componente_para_presentacion_api(componente: Mapping[str, object]) -> dict[str, object]:
    resultado = _campos_para_presentacion_api(
        componente,
        (
            "tipo",
            "id_pendiente",
            "id_fuente",
            "id_canonico",
            "id_competencia",
            "id_habilidad",
            "id_herramienta",
            "nombre",
            "nombre_fuente",
            "nombre_propuesto",
            "nombre_catalogo",
            "nombre_canonico",
            "display_name",
            "estado_nombre",
            "descripcion",
            "description",
            "descripcion_fuente",
            "estado_resolucion",
            "decision",
            "canonical",
        ),
    )
    propuesta = componente.get("propuesta")
    if isinstance(propuesta, Mapping):
        resultado["propuesta"] = _campos_para_presentacion_api(
            propuesta, ("id", "nombre", "descripcion", "tipo")
        )
    for campo in ("id_pendientes", "id_fuentes", "nombres_propuestos", "flags"):
        if campo in componente:
            resultado[campo] = _textos_para_presentacion_api(componente.get(campo))
    if "source_identity" in componente:
        resultado["source_identity"] = _identidad_para_presentacion_api(
            componente.get("source_identity")
        )
    return resultado


def _relacion_para_presentacion_api(relacion: Mapping[str, object]) -> dict[str, object]:
    resultado = _campos_para_presentacion_api(
        relacion,
        (*RELATION_KEYS, *IDENTITY_FIELDS, "source_ref", "archivo", "id_logro"),
    )
    if "source_identity" in relacion:
        resultado["source_identity"] = _identidad_para_presentacion_api(
            relacion.get("source_identity")
        )
    return resultado


def _alias_para_presentacion_api(alias: Mapping[str, object]) -> dict[str, object]:
    resultado = _campos_para_presentacion_api(alias, ("id_pendiente", "representative_id"))
    if "evidence" in alias:
        resultado["evidence"] = _textos_para_presentacion_api(alias.get("evidence"))
    if "source_identity" in alias:
        resultado["source_identity"] = _identidad_para_presentacion_api(
            alias.get("source_identity")
        )
    return resultado


def _pendientes_para_presentacion_api(valor: object) -> object:
    if isinstance(valor, list):
        return filas_para_presentacion_api(valor)
    if isinstance(valor, Mapping):
        return _campos_para_presentacion_api(
            valor, ("total", "pendientes_por_decidir", "accepted", "remaining_pending")
        )
    return valor


def _identidad_para_presentacion_api(valor: object) -> dict[str, str]:
    identidad = valor if isinstance(valor, Mapping) else {}
    return {
        campo: _texto(identidad.get(campo))
        for campo in IDENTITY_FIELDS
        if _texto(identidad.get(campo))
    }


def _campos_para_presentacion_api(
    origen: Mapping[str, object], campos: Sequence[str]
) -> dict[str, object]:
    return {campo: origen[campo] for campo in campos if campo in origen}


def _lista_para_presentacion_api(valor: object) -> list[object]:
    return list(valor) if isinstance(valor, list) else []


def _lista_mapeos_para_presentacion_api(valor: object) -> list[Mapping[str, object]]:
    return [item for item in _lista_para_presentacion_api(valor) if isinstance(item, Mapping)]


def _textos_para_presentacion_api(valor: object) -> list[str]:
    valores = valor if isinstance(valor, list) else [valor]
    return [texto for item in valores if (texto := _texto(item))]


def _texto(valor: object) -> str:
    return re.sub(r"\s+", " ", str(valor or "")).strip()
