"""Source-scoped CHH packages used by the human approval checkpoint."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence

from agente.normalizador.modelos import Hallazgo
from agente.normalizador.silabos import paquetes_relaciones as _paquetes_relaciones
from agente.normalizador.silabos.clasificacion import estado_clasificacion

PACKAGE_ID_FIELD = _paquetes_relaciones.PACKAGE_ID_FIELD
PACKAGE_ID_ALIASES = _paquetes_relaciones.PACKAGE_ID_ALIASES
PACKAGE_SOURCE_KEY_FIELD = _paquetes_relaciones.PACKAGE_SOURCE_KEY_FIELD
PACKAGE_SOURCE_IDENTITY_FIELD = _paquetes_relaciones.PACKAGE_SOURCE_IDENTITY_FIELD
_REQUIRED_IDENTITY_FIELDS = _paquetes_relaciones._REQUIRED_IDENTITY_FIELDS
SOURCE_RELATION_ID_FIELD = _paquetes_relaciones.SOURCE_RELATION_ID_FIELD
IDENTITY_FIELDS = _paquetes_relaciones.IDENTITY_FIELDS
RELATION_KEYS = _paquetes_relaciones.RELATION_KEYS
_SOURCE_RELATIONS_FILE = _paquetes_relaciones._SOURCE_RELATIONS_FILE
_IdentityKey = _paquetes_relaciones._IdentityKey
_CourseSyllabusKey = _paquetes_relaciones._CourseSyllabusKey
_PackageAssemblyIndex = _paquetes_relaciones._PackageAssemblyIndex
_index_package_assembly = _paquetes_relaciones._index_package_assembly
_identity_key = _paquetes_relaciones._identity_key
_base_identity_key = _paquetes_relaciones._base_identity_key
_identity_from_key = _paquetes_relaciones._identity_from_key
_row_identity_key = _paquetes_relaciones._row_identity_key
_identity_buckets = _paquetes_relaciones._identity_buckets
_value_buckets = _paquetes_relaciones._value_buckets
_source_relation_buckets = _paquetes_relaciones._source_relation_buckets
_source_relations_for_key = _paquetes_relaciones._source_relations_for_key
_relation_buckets = _paquetes_relaciones._relation_buckets
_ordered_rows = _paquetes_relaciones._ordered_rows
_scoped_relations_for_key = _paquetes_relaciones._scoped_relations_for_key
_scoped_canonical_ids = _paquetes_relaciones._scoped_canonical_ids
_relation_matches_scoped_ids = _paquetes_relaciones._relation_matches_scoped_ids
_relation_scope_matches = _paquetes_relaciones._relation_scope_matches
_source_row_matches_package = _paquetes_relaciones._source_row_matches_package
_source_row_matches_relation_unit = _paquetes_relaciones._source_row_matches_relation_unit
_source_relation_matches = _paquetes_relaciones._source_relation_matches
_source_relations_for_identity = _paquetes_relaciones._source_relations_for_identity
_scope_matches = _paquetes_relaciones._scope_matches
_identity_complete = _paquetes_relaciones._identity_complete
_identity_equal = _paquetes_relaciones._identity_equal
_first = _paquetes_relaciones._first
_text = _paquetes_relaciones._text
_mapping = _paquetes_relaciones._mapping

_TYPE_ORDER = _paquetes_relaciones._TYPE_ORDER
_UNRESOLVED_RESOLUTION_STATES = _paquetes_relaciones._UNRESOLVED_RESOLUTION_STATES
_SOURCE_FILES = _paquetes_relaciones._SOURCE_FILES
_CATALOGS = _paquetes_relaciones._CATALOGS
_TECHNICAL_NAME = _paquetes_relaciones._TECHNICAL_NAME
_HASH_NAME = _paquetes_relaciones._HASH_NAME
_project_components = _paquetes_relaciones.project_components
_relaciones_canonicas = _paquetes_relaciones._relaciones_canonicas
_propuesta_pendiente = _paquetes_relaciones._propuesta_pendiente
_add_source_components = _paquetes_relaciones._add_source_components
_catalog_names_by_id = _paquetes_relaciones._catalog_names_by_id
_add_canonical_components = _paquetes_relaciones._add_canonical_components
_component_from_row = _paquetes_relaciones._component_from_row
_unique_components = _paquetes_relaciones._unique_components
_component_identifier = _paquetes_relaciones._component_identifier
_component_name = _paquetes_relaciones._component_name
_component_key = _paquetes_relaciones._component_key
_component_source_key = _paquetes_relaciones._component_source_key
_has_structured_proposal = _paquetes_relaciones._has_structured_proposal
_is_provisional_component = _paquetes_relaciones._is_provisional_component
_with_component_provenance = _paquetes_relaciones._with_component_provenance
_component_provenance = _paquetes_relaciones._component_provenance
_merge_components = _paquetes_relaciones._merge_components
_normalized_name = _paquetes_relaciones._normalized_name
_usable_display_name = _paquetes_relaciones._usable_display_name
Counter = _paquetes_relaciones.Counter
re = _paquetes_relaciones.re
unicodedata = _paquetes_relaciones.unicodedata


class IdentidadFuenteIncompleta(ValueError):
    """A package cannot be assembled without its complete source identity."""


def identidad_fuente_chh(
    fila: Mapping[str, object], *, id_ejecucion: str = "", carrera: str = "", periodo: str = ""
) -> dict[str, str]:
    """Build a collision-safe identity; a raw source skill ID is never sufficient."""
    nested = _mapping(fila.get(PACKAGE_SOURCE_IDENTITY_FIELD))
    source_skill = _first(
        fila,
        "id_habilidad_fuente",
        "source_skill_id",
        "id_habilidad_source",
    ) or _first(nested, "id_habilidad_fuente")
    syllabus = _first(fila, "id_silabo", "syllabus_id", "silabo") or _first(nested, "id_silabo")
    identity = {
        "id_ejecucion": _first(fila, "id_ejecucion", "execution_id")
        or _first(nested, "id_ejecucion")
        or id_ejecucion,
        "carrera": _first(fila, "carrera", "career") or _first(nested, "carrera") or carrera,
        "periodo": _first(fila, "periodo", "period") or _first(nested, "periodo") or periodo,
        "id_curso": _first(fila, "id_curso", "course_id") or _first(nested, "id_curso"),
        "id_silabo": syllabus,
        "id_habilidad_fuente": source_skill,
        SOURCE_RELATION_ID_FIELD: _first(
            fila, SOURCE_RELATION_ID_FIELD, "id_relacion_fuente", "source_relation_id"
        )
        or _first(nested, SOURCE_RELATION_ID_FIELD, "id_relacion_fuente", "source_relation_id"),
    }
    missing = [key for key in _REQUIRED_IDENTITY_FIELDS if not identity[key]]
    if missing:
        raise IdentidadFuenteIncompleta(
            "Identidad de paquete CHH incompleta; faltan: " + ", ".join(missing) + "."
        )
    return identity


def clave_fuente_chh(identity: Mapping[str, str]) -> str:
    payload = {key: _text(identity.get(key)) for key in _REQUIRED_IDENTITY_FIELDS}
    if relation_id := _text(identity.get(SOURCE_RELATION_ID_FIELD)):
        payload[SOURCE_RELATION_ID_FIELD] = relation_id
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def id_paquete_chh(identity: Mapping[str, str]) -> str:
    digest = hashlib.sha256(clave_fuente_chh(identity).encode("utf-8")).hexdigest()
    return f"PKG_CHH_{digest[:20]}"


def preparar_fila_paquete(
    fila: Mapping[str, object], *, id_ejecucion: str = "", carrera: str = "", periodo: str = ""
) -> dict[str, object]:
    prepared = dict(fila)
    identity = identidad_fuente_chh(
        prepared, id_ejecucion=id_ejecucion, carrera=carrera, periodo=periodo
    )
    package_id = id_paquete_chh(identity)
    prepared.update(
        {
            PACKAGE_ID_FIELD: package_id,
            "package_id": package_id,
            PACKAGE_SOURCE_KEY_FIELD: clave_fuente_chh(identity),
            "clave_paquete_chh": clave_fuente_chh(identity),
            PACKAGE_SOURCE_IDENTITY_FIELD: identity,
            "execution_id": identity["id_ejecucion"],
            "career": identity["carrera"],
            "period": identity["periodo"],
        }
    )
    return prepared


def ensamblar_paquetes_chh(
    filas: Sequence[Mapping[str, object]],
    *,
    id_ejecucion: str = "",
    carrera: str = "",
    periodo: str = "",
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    relaciones: Sequence[Mapping[str, object]] | None = None,
    archivos: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
) -> list[dict[str, object]]:
    prepared = [
        preparar_fila_paquete(row, id_ejecucion=id_ejecucion, carrera=carrera, periodo=periodo)
        for row in filas
    ]
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in prepared:
        grouped.setdefault(_first(row, *PACKAGE_ID_ALIASES), []).append(row)
    index = _index_package_assembly(
        [_mapping(rows[0].get(PACKAGE_SOURCE_IDENTITY_FIELD)) for rows in grouped.values() if rows],
        fuentes=fuentes,
        relaciones=relaciones,
        archivos=archivos,
    )
    return [
        _assemble_one(
            package_id,
            rows,
            fuentes=fuentes,
            relaciones=relaciones,
            archivos=archivos,
            index=index,
        )
        for package_id, rows in sorted(grouped.items())
    ]


def construir_paquetes_chh(
    filas: Sequence[Mapping[str, object]],
    *,
    id_ejecucion: str = "",
    carrera: str = "",
    periodo: str = "",
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    relaciones: Sequence[Mapping[str, object]] | None = None,
    archivos: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
) -> list[dict[str, object]]:
    return ensamblar_paquetes_chh(
        filas,
        id_ejecucion=id_ejecucion,
        carrera=carrera,
        periodo=periodo,
        fuentes=fuentes,
        relaciones=relaciones,
        archivos=archivos,
    )


def validar_integridad_paquetes_chh(
    paquetes: Sequence[Mapping[str, object]],
) -> tuple[Hallazgo, ...]:
    """Validate package-local coverage. A competency-only package is valid."""
    findings: list[Hallazgo] = []
    for package in paquetes:
        package_id = _first(package, *PACKAGE_ID_ALIASES)
        identity = _mapping(package.get(PACKAGE_SOURCE_IDENTITY_FIELD))
        if not _identity_complete(identity):
            findings.append(
                _finding(
                    "PAQUETE_IDENTIDAD_INCOMPLETA",
                    "El paquete debe conservar toda la identidad de su fuente.",
                    package_id,
                )
            )
        else:
            expected_package_id = id_paquete_chh(
                {key: _text(identity.get(key)) for key in IDENTITY_FIELDS}
            )
            if package_id != expected_package_id:
                findings.append(
                    _finding(
                        "PAQUETE_ID_INVALIDO",
                        "El id del paquete no coincide con su identidad fuente.",
                        package_id or expected_package_id,
                    )
                )
        grouped = _mapping(package.get("componentes"))
        competencies = _components(package, grouped, "competencias", "competency")
        skills = _components(package, grouped, "habilidades", "skills")
        tools = _components(package, grouped, "herramientas", "tools")
        pending_hitl = _package_waiting_for_decision(package)
        for blocker in _list_value(package.get("competency_blockers")):
            if not isinstance(blocker, Mapping):
                continue
            findings.append(
                _finding(
                    _text(blocker.get("code")) or "COMPETENCY_SOURCE_MAPPING_REQUIRED",
                    "La referencia de competencia fuente requiere un mapeo canónico real: "
                    + _text(blocker.get("id_competencia_fuente")),
                    package_id,
                )
            )
        competency_ids = _component_ids(competencies, "competencia")
        skill_ids = _component_ids(skills, "habilidad")
        tool_ids = _component_ids(tools, "herramienta")
        if not competencies:
            findings.append(
                _finding(
                    "PAQUETE_SIN_COMPETENCIA",
                    "Todo paquete CHH debe contener una competencia.",
                    package_id,
                )
            )
            if skills:
                findings.append(
                    _finding(
                        "PAQUETE_HABILIDAD_SIN_COMPETENCIA",
                        "Una habilidad sin competencia es un error de estructura del paquete.",
                        package_id,
                    )
                )
        parsed: list[tuple[str, ...]] = []
        for index, relation in enumerate(_relationships(package), start=1):
            values = _relation_values(relation)
            if values is None or not values[1] or not values[2] or not values[3] or not values[4]:
                findings.append(
                    _finding(
                        "PAQUETE_RELACION_INVALIDA",
                        "Una relación debe conservar curso, sílabo, competencia y habilidad.",
                        package_id,
                        fila=index,
                    )
                )
                continue
            if isinstance(relation, Mapping) and not _scope_matches(relation, identity):
                findings.append(
                    _finding(
                        "PAQUETE_RELACION_FUERA_DE_SCOPE",
                        "Las relaciones deben pertenecer al mismo paquete fuente.",
                        package_id,
                        fila=index,
                    )
                )
            if (
                values[3] not in competency_ids
                or values[4] not in skill_ids
                or (values[5] and values[5] not in tool_ids)
            ):
                findings.append(
                    _finding(
                        "PAQUETE_RELACION_REFERENCIA_INVALIDA",
                        "Una relación apunta a un componente ausente del paquete.",
                        package_id,
                        fila=index,
                    )
                )
            parsed.append(values)
        skills_without_relation = skill_ids - {
            value[4] for value in parsed if value[3] in competency_ids and value[4] in skill_ids
        }
        if skills and not pending_hitl and skills_without_relation:
            findings.append(
                _finding(
                    "PAQUETE_HABILIDAD_SIN_RELACION",
                    "Toda habilidad presente debe conservar una relación del paquete.",
                    package_id,
                )
            )
        tools_without_chain = tool_ids - {
            value[5]
            for value in parsed
            if value[3] in competency_ids and value[4] in skill_ids and value[5] in tool_ids
        }
        if tools and not pending_hitl and tools_without_chain:
            findings.append(
                _finding(
                    "PAQUETE_HERRAMIENTA_SIN_RELACION",
                    "Toda herramienta presente debe conservar una relación con "
                    "habilidad y competencia.",
                    package_id,
                )
            )
        for row in _rows(package):
            row_identity = _mapping(row.get(PACKAGE_SOURCE_IDENTITY_FIELD))
            if row_identity and identity and not _identity_equal(row_identity, identity):
                findings.append(
                    _finding(
                        "PAQUETE_FUENTE_FUERA_DE_SCOPE",
                        "Las filas fuente deben pertenecer al mismo paquete.",
                        package_id,
                    )
                )
                break
    return tuple(findings)


def validar_paquetes_chh(paquetes: Sequence[Mapping[str, object]]) -> tuple[Hallazgo, ...]:
    return validar_integridad_paquetes_chh(paquetes)


def revision_paquetes_chh(paquetes: Sequence[Mapping[str, object]]) -> str:
    snapshot = [
        {
            PACKAGE_ID_FIELD: _first(package, *PACKAGE_ID_ALIASES),
            "decision": _text(package.get("decision")),
            "rows": sorted(_text(row.get("id_pendiente")) for row in _rows(package)),
        }
        for package in paquetes
    ]
    payload = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


assemble_chh_packages = ensamblar_paquetes_chh
validate_chh_packages = validar_integridad_paquetes_chh



def _assemble_one(
    package_id: str,
    rows: Sequence[Mapping[str, object]],
    *,
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None,
    relaciones: Sequence[Mapping[str, object]] | None,
    archivos: Mapping[str, Sequence[Mapping[str, object]]] | None,
    index: _PackageAssemblyIndex | None = None,
) -> dict[str, object]:
    ordered = sorted((dict(row) for row in rows), key=_row_sort_key)
    identity = _mapping(ordered[0].get(PACKAGE_SOURCE_IDENTITY_FIELD))
    identity_text = {key: _text(identity.get(key)) for key in IDENTITY_FIELDS}
    identity_key = _identity_key(identity)
    indexed_source_relations = index.source_relations.get(identity_key, ()) if index else ()
    source_package_relations = relaciones_fuente_para_paquete_chh(
        indexed_source_relations if index else (fuentes or {}).get(_SOURCE_RELATIONS_FILE, ()),
        identity,
        package_id=package_id,
    )
    by_type = _project_components(
        ordered,
        identity,
        fuentes=fuentes,
        archivos=archivos,
        source_relations=source_package_relations,
        source_rows=index.sources.get(identity_key) if index else None,
        scoped_relations=index.coverage_relations.get(identity_key) if index else None,
        preselected=bool(index),
        is_unresolved_row=_is_unresolved_row,
        source_row_matches_package=_source_row_matches_package,
        relation_scope_matches=_relation_scope_matches,
    )
    aliases: list[dict[str, object]] = []
    for row in ordered:
        if not estado_clasificacion(row).auto_deduplicated:
            continue
        evidence = row.get("evidencia")
        aliases.append(
            {
                "id_pendiente": _text(row.get("id_pendiente")),
                "representative_id": _text(estado_clasificacion(row).representative_id),
                "evidence": list(evidence) if isinstance(evidence, list) else [],
                PACKAGE_SOURCE_IDENTITY_FIELD: dict(identity),
            }
        )
    competency_blockers: list[dict[str, str]] = []
    for source_relation in source_package_relations:
        source_competency_id = _text(source_relation.get("id_competencia_fuente"))
        if not source_competency_id or _text(source_relation.get("id_competencia_canonica")):
            continue
        blocker = {
            "code": "COMPETENCY_SOURCE_MAPPING_REQUIRED",
            "id_competencia_fuente": source_competency_id,
            "id_cob_curricular": _text(source_relation.get("id_cob_curricular")),
        }
        if blocker not in competency_blockers:
            competency_blockers.append(blocker)
    open_rows = [row for row in ordered if _requires_human_decision(row)]
    unresolved_rows = [row for row in ordered if _is_unresolved_row(row)]
    decisions = {
        _text(row.get("decision")).upper() for row in ordered if _text(row.get("decision"))
    }
    decision = next(iter(decisions)) if len(decisions) == 1 else "MIXED" if decisions else None
    package_relations = relaciones_para_paquete_chh(
        index.package_relations.get(identity_key, ()) if index else relaciones or (),
        identity,
        fuentes=fuentes,
        package_id=package_id,
        source_relations=source_package_relations,
        preselected=bool(index),
    )
    package_relations.sort(key=lambda row: tuple(_text(row.get(key)) for key in RELATION_KEYS))
    components = {
        "competencias": by_type["competencia"],
        "habilidades": by_type["habilidad"],
        "herramientas": by_type["herramienta"],
    }
    # These three fields are the package contract consumed by new callers.
    # ``relaciones`` and ``componentes`` remain compatibility aliases for the
    # existing CSV/HITL pipeline, but must not be combined to infer a cartesian
    # CHH relation in a presentation layer.
    # A pending proposal is source evidence, not an accepted canonical edge.
    # Keep the raw relation for HITL, but never project it as canonical until
    # every row in this source package is resolved.
    relaciones_canonicas = (
        []
        if unresolved_rows or competency_blockers
        else _relaciones_canonicas(package_relations, components)
    )
    propuestas_pendientes = [
        _propuesta_pendiente(row)
        for row in ordered
        if _is_unresolved_row(row) and not estado_clasificacion(row).auto_deduplicated
    ]
    structural_error = not components["competencias"]
    return {
        PACKAGE_ID_FIELD: package_id,
        "package_id": package_id,
        PACKAGE_SOURCE_KEY_FIELD: clave_fuente_chh(identity_text),
        "clave_paquete_chh": clave_fuente_chh(identity_text),
        PACKAGE_SOURCE_IDENTITY_FIELD: dict(identity),
        **{key: _text(identity.get(key)) for key in IDENTITY_FIELDS},
        "componentes": components,
        **components,
        "relaciones": package_relations,
        "relationships": package_relations,
        "relaciones_canonicas": relaciones_canonicas,
        "propuestas_pendientes": propuestas_pendientes,
        "competency_blockers": competency_blockers,
        "source_relationships": source_package_relations,
        "source_evidence": {
            "relationships": source_package_relations,
            "rows": ordered,
        },
        "filas": ordered,
        "legacy_rows": ordered,
        "id_pendientes": [_text(row.get("id_pendiente")) for row in ordered],
        "manual_review_rows": [_text(row.get("id_pendiente")) for row in open_rows],
        "alias_ids": [_text(alias["id_pendiente"]) for alias in aliases],
        "aliases": aliases,
        "exact_duplicate_aliases": aliases,
        "flags": sorted(
            {
                _text(flag)
                for row in ordered
                for flag in estado_clasificacion(row).flags
                if _text(flag)
            }
        ),
        "requires_human_decision": bool(open_rows or competency_blockers),
        "requiere_decision": bool(open_rows or competency_blockers),
        "decision": decision,
        "package_decision": decision,
        "decision_state": (
            "STRUCTURAL_ERROR"
            if structural_error
            else "PENDING"
            if unresolved_rows or competency_blockers
            else "MIXED"
            if decision == "MIXED"
            else "DECIDED"
        ),
    }



def _nombre_componente(componente: Mapping[str, object]) -> str:
    return _text(
        componente.get("nombre")
        or componente.get("display_name")
        or componente.get("nombre_propuesto")
        or componente.get("nombre_fuente")
        or componente.get("nombre_canonico")
    )


def _componentes_unicos(valor: object) -> list[Mapping[str, object]]:
    vistos: set[str] = set()
    unicos: list[Mapping[str, object]] = []
    for componente in valor if isinstance(valor, list) else []:
        if not isinstance(componente, Mapping):
            continue
        nombre = _nombre_componente(componente)
        if not nombre:
            # A decidible triple needs a readable name for every component.
            continue
        clave = _normalized_name(nombre)
        if not clave or clave in vistos:
            continue
        vistos.add(clave)
        unicos.append(componente)
    return unicos


def _ids_de_componente(componente: Mapping[str, object]) -> set[str]:
    ids: set[str] = set()
    for campo in ("id_pendiente", "id_pendientes", "id_canonico", "id_fuente", "id_fuentes"):
        valor = componente.get(campo)
        for item in valor if isinstance(valor, list) else [valor]:
            texto_item = _text(item)
            if texto_item:
                ids.add(texto_item)
    return ids


def _fila_pertenece_a_componente(
    fila: Mapping[str, object], componente: Mapping[str, object]
) -> bool:
    id_fila = _text(fila.get("id_pendiente"))
    if id_fila and id_fila in _ids_de_componente(componente):
        return True
    propuesta = fila.get("propuesta")
    nombre_fila = _text(propuesta.get("nombre") if isinstance(propuesta, Mapping) else "")
    nombre_componente = _nombre_componente(componente)
    return bool(nombre_fila) and _normalized_name(nombre_fila) == _normalized_name(nombre_componente)


def _referencia_coincide(referencia: object, componente: Mapping[str, object]) -> bool:
    if isinstance(referencia, Mapping):
        ref_id = _text(referencia.get("id"))
        ref_nombre = _text(referencia.get("nombre"))
    else:
        ref_id = ""
        ref_nombre = _text(referencia)
    if not ref_id and not ref_nombre:
        return True
    ids = _ids_de_componente(componente)
    nombre_componente = _normalized_name(_nombre_componente(componente))
    return (bool(ref_id) and ref_id in ids) or (
        bool(ref_nombre) and _normalized_name(ref_nombre) == nombre_componente
    )


def _componentes_del_triple(
    competencia: Mapping[str, object],
    habilidad: Mapping[str, object],
    herramienta: Mapping[str, object],
) -> dict[str, Mapping[str, object]]:
    return {
        "competencias": competencia,
        "habilidades": habilidad,
        "herramientas": herramienta,
    }


def _relaciones_filtradas(
    relaciones: object, componentes: dict[str, Mapping[str, object]]
) -> list[object]:
    claves = {
        "id_competencia": componentes["competencias"],
        "id_habilidad": componentes["habilidades"],
        "id_herramienta": componentes["herramientas"],
    }
    resultado: list[object] = []
    for relacion in relaciones if isinstance(relaciones, list) else []:
        if not isinstance(relacion, Mapping):
            resultado.append(relacion)
            continue
        if all(
            _referencia_coincide(_text(relacion.get(clave)), componente)
            for clave, componente in claves.items()
        ):
            resultado.append(relacion)
    return resultado


def _canonicas_filtradas(
    canonicas: object, componentes: dict[str, Mapping[str, object]]
) -> list[object]:
    pares = (
        ("competencia", componentes["competencias"]),
        ("habilidad", componentes["habilidades"]),
        ("herramienta", componentes["herramientas"]),
    )
    resultado: list[object] = []
    for triple in canonicas if isinstance(canonicas, list) else []:
        if not isinstance(triple, Mapping):
            resultado.append(triple)
            continue
        if all(_referencia_coincide(triple.get(tipo), componente) for tipo, componente in pares):
            resultado.append(triple)
    return resultado


def _triples_de_paquete(
    package: Mapping[str, object],
) -> list[tuple[Mapping[str, object], Mapping[str, object], Mapping[str, object]]]:
    grupos = {
        "competencias": _componentes_unicos(package.get("competencias")),
        "habilidades": _componentes_unicos(package.get("habilidades")),
        "herramientas": _componentes_unicos(package.get("herramientas")),
    }
    if any(not valores for valores in grupos.values()):
        return []
    return [
        (competencia, habilidad, herramienta)
        for competencia in grupos["competencias"]
        for habilidad in grupos["habilidades"]
        for herramienta in grupos["herramientas"]
    ]


def _clave_triple(
    competencia: Mapping[str, object],
    habilidad: Mapping[str, object],
    herramienta: Mapping[str, object],
) -> str:
    partes = "|".join(
        _normalized_name(_nombre_componente(componente))
        or _text(componente.get("id_canonico") or componente.get("id_pendiente"))
        for componente in (competencia, habilidad, herramienta)
    )
    return hashlib.sha256(partes.encode("utf-8")).hexdigest()[:12]


def _fan_de_triple(
    package: Mapping[str, object],
    competencia: Mapping[str, object],
    habilidad: Mapping[str, object],
    herramienta: Mapping[str, object],
    *,
    identidad: Mapping[str, str],
    package_id: str,
) -> dict[str, object] | None:
    """One package must stay a single unique CHH triple; this projects one fan."""

    filas = [
        row
        for row in (package.get("filas") or [])
        if isinstance(row, Mapping)
        and any(
            _fila_pertenece_a_componente(row, componente)
            for componente in (competencia, habilidad, herramienta)
        )
    ]
    if not filas:
        return None
    ids_filas = {_text(row.get("id_pendiente")) for row in filas if _text(row.get("id_pendiente"))}
    componentes = _componentes_del_triple(competencia, habilidad, herramienta)
    fan = dict(package)
    fan[PACKAGE_ID_FIELD] = package_id
    fan["package_id"] = package_id
    fan[PACKAGE_SOURCE_KEY_FIELD] = clave_fuente_chh(identidad)
    fan["clave_paquete_chh"] = clave_fuente_chh(identidad)
    fan[PACKAGE_SOURCE_IDENTITY_FIELD] = dict(identidad)
    fan.update({key: _text(identidad.get(key)) for key in IDENTITY_FIELDS})
    fan["componentes"] = {nombre: [componente] for nombre, componente in componentes.items()}
    for nombre, componente in componentes.items():
        fan[nombre] = [componente]
    fan["filas"] = filas
    fan["legacy_rows"] = filas
    fan["id_pendientes"] = [row.get("id_pendiente") for row in filas]
    fan["manual_review_rows"] = [
        row_id
        for row_id in (package.get("manual_review_rows") or [])
        if _text(row_id) in ids_filas
    ]
    fan["aliases"] = [
        alias
        for alias in (package.get("aliases") or [])
        if isinstance(alias, Mapping) and _text(alias.get("id_pendiente")) in ids_filas
    ]
    fan["exact_duplicate_aliases"] = fan["aliases"]
    fan["alias_ids"] = [alias.get("id_pendiente") for alias in fan["aliases"]]
    fan["propuestas_pendientes"] = [
        propuesta
        for propuesta in (package.get("propuestas_pendientes") or [])
        if isinstance(propuesta, Mapping)
        and _text(propuesta.get("id_pendiente")) in ids_filas
    ]
    fan["relaciones"] = _relaciones_filtradas(package.get("relaciones"), componentes)
    fan["relationships"] = fan["relaciones"]
    evidencia_fuente = dict(package.get("source_evidence") or {})
    fan["source_relationships"] = _relaciones_filtradas(
        evidencia_fuente.get("relationships"), componentes
    )
    evidencia_fuente["relationships"] = fan["source_relationships"]
    evidencia_fuente["rows"] = filas
    fan["source_evidence"] = evidencia_fuente
    fan["relaciones_canonicas"] = _canonicas_filtradas(
        package.get("relaciones_canonicas"), componentes
    )
    decisiones = {
        _text(row.get("decision")).upper() for row in filas if _text(row.get("decision"))
    }
    decision = next(iter(decisiones)) if len(decisiones) == 1 else "MIXED" if decisiones else None
    blockers = package.get("competency_blockers") or []
    pendientes_fan = bool(fan["propuestas_pendientes"])
    fan["decision"] = decision
    fan["package_decision"] = decision
    fan["requires_human_decision"] = bool(pendientes_fan or blockers)
    fan["requiere_decision"] = fan["requires_human_decision"]
    fan["decision_state"] = (
        "PENDING"
        if pendientes_fan or blockers or decision is None
        else "MIXED"
        if decision == "MIXED"
        else "DECIDED"
    )
    return fan


def _abrir_paquetes_por_triple(package: Mapping[str, object]) -> list[dict[str, object]]:
    """Split a source package into one unique CHH triple per package.

    Only complete triples survive: a package without competencia, habilidad or
    herramienta is not actionable and stays as pending rows for HITL review.
    """

    triples = _triples_de_paquete(package)
    if not triples:
        return []
    identidad_base = _mapping(package.get(PACKAGE_SOURCE_IDENTITY_FIELD)) or {
        key: _text(package.get(key)) for key in IDENTITY_FIELDS
    }
    if len(triples) == 1:
        fan = _fan_de_triple(
            package,
            *triples[0],
            identidad=identidad_base,
            package_id=_first(package, *PACKAGE_ID_ALIASES),
        )
        return [fan or dict(package)]
    fans: list[dict[str, object]] = []
    for competencia, habilidad, herramienta in triples:
        identidad = dict(identidad_base)
        relacion_fuente = _text(identidad.get(SOURCE_RELATION_ID_FIELD))
        clave = _clave_triple(competencia, habilidad, herramienta)
        identidad[SOURCE_RELATION_ID_FIELD] = (
            f"{relacion_fuente}:{clave}" if relacion_fuente else f"TRIPLE:{clave}"
        )
        fan = _fan_de_triple(
            package,
            competencia,
            habilidad,
            herramienta,
            identidad=identidad,
            package_id=id_paquete_chh(identidad),
        )
        if fan:
            fans.append(fan)
    return fans


def relaciones_fuente_para_paquete_chh(
    relaciones: Sequence[Mapping[str, object]],
    identity: Mapping[str, object],
    *,
    package_id: str = "",
) -> list[dict[str, object]]:
    return _paquetes_relaciones.relaciones_fuente_para_paquete_chh(
        relaciones, identity, package_id=package_id, id_paquete=id_paquete_chh
    )


def _components(
    package: Mapping[str, object], grouped: Mapping[str, object], key: str, alias: str
) -> list[Mapping[str, object]]:
    values = package.get(key)
    grouped_values = grouped.get(key) or grouped.get(alias)
    if not isinstance(values, list) or not values:
        values = grouped_values
    elif isinstance(grouped_values, list) and not any(
        _text(
            value.get("id_canonico")
            or value.get("id_competencia")
            or value.get("id_habilidad")
            or value.get("id_herramienta")
        )
        for value in values
        if isinstance(value, Mapping)
    ):
        values = grouped_values
    return (
        [value for value in values if isinstance(value, Mapping)]
        if isinstance(values, list)
        else []
    )


def _component_ids(values: Sequence[Mapping[str, object]], kind: str) -> set[str]:
    return {
        _text(value.get(f"id_{kind}") or value.get("id_canonico"))
        for value in values
        if _text(value.get(f"id_{kind}") or value.get("id_canonico"))
    }


def _relationships(package: Mapping[str, object]) -> list[Mapping[str, object] | Sequence[object]]:
    value = package.get("relaciones") or package.get("relationships")
    return (
        [item for item in value if isinstance(item, (Mapping, tuple, list))]
        if isinstance(value, list)
        else []
    )


def _relation_values(value: Mapping[str, object] | Sequence[object]) -> tuple[str, ...] | None:
    if isinstance(value, Mapping):
        values = tuple(_text(value.get(key)) for key in RELATION_KEYS)
    elif isinstance(value, (tuple, list)) and len(value) in (5, 6):
        values = tuple(_text(item) for item in value)
        if len(values) == 5:
            values = ("",) + values
    else:
        return None
    return values if any(values) else None



def relaciones_para_paquete_chh(
    relaciones: Sequence[Mapping[str, object]],
    identity: Mapping[str, object],
    *,
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    package_id: str = "",
    source_relations: Sequence[Mapping[str, object]] | None = None,
    preselected: bool = False,
) -> list[dict[str, object]]:
    return _paquetes_relaciones.relaciones_para_paquete_chh(
        relaciones,
        identity,
        fuentes=fuentes,
        package_id=package_id,
        source_relations=source_relations,
        preselected=preselected,
        id_paquete=id_paquete_chh,
    )


def _rows(package: Mapping[str, object]) -> list[Mapping[str, object]]:
    value = package.get("filas") or package.get("legacy_rows")
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _package_waiting_for_decision(package: Mapping[str, object]) -> bool:
    return bool(package.get("requires_human_decision") or package.get("requiere_decision")) or (
        _text(package.get("decision_state")).upper() == "PENDING"
    )


def _requires_human_decision(row: Mapping[str, object]) -> bool:
    if estado_clasificacion(row).auto_deduplicated:
        return False
    if not _text(row.get("decision")) and estado_clasificacion(row).requires_human_decision:
        return True
    resolution = _text(row.get("estado_resolucion")).upper()
    return resolution in _UNRESOLVED_RESOLUTION_STATES - {"MANTENIDA_PENDIENTE"}


def _is_unresolved_row(row: Mapping[str, object]) -> bool:
    if estado_clasificacion(row).auto_deduplicated:
        return False
    resolution = _text(row.get("estado_resolucion")).upper()
    if resolution in _UNRESOLVED_RESOLUTION_STATES or resolution.startswith("PENDIENTE_"):
        return True
    return _text(row.get("decision")).upper() == "KEEP_PENDING"


def _row_sort_key(row: Mapping[str, object]) -> tuple[object, ...]:
    kind, proposal = _text(row.get("tipo")).casefold(), _mapping(row.get("propuesta"))
    return (
        _TYPE_ORDER.get(kind, 99),
        _text(proposal.get("nombre") or proposal.get("id")).casefold(),
        _text(row.get("id_pendiente")),
    )



def _list_value(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []


def _finding(code: str, message: str, package_id: str, *, fila: int | None = None) -> Hallazgo:
    return Hallazgo(
        codigo=code,
        severidad="error",
        mensaje=message,
        hoja="cobertura_curricular.csv",
        fila=fila,
        detalle=package_id,
    )
