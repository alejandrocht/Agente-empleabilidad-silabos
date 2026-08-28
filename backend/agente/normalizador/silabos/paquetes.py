"""Source-scoped CHH packages used by the human approval checkpoint."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence

from agente.normalizador.modelos import Hallazgo

PACKAGE_ID_FIELD = "id_paquete_chh"
PACKAGE_ID_ALIASES = (PACKAGE_ID_FIELD, "package_id", "id_paquete")
PACKAGE_SOURCE_KEY_FIELD = "package_source_key"
PACKAGE_SOURCE_IDENTITY_FIELD = "source_identity"
IDENTITY_FIELDS = (
    "id_ejecucion",
    "carrera",
    "periodo",
    "id_curso",
    "id_silabo",
    "id_habilidad_fuente",
)
RELATION_KEYS = (
    "id_cob_curricular",
    "id_curso",
    "id_silabo",
    "id_competencia",
    "id_habilidad",
    "id_herramienta",
)
_TYPE_ORDER = {"competencia": 0, "habilidad": 1, "herramienta": 2}
_SOURCE_FILES = {
    "competencia": (
        "competencias_fuente.jsonl",
        "id_competencia_fuente",
        "id_competencia_canonica",
        "nombre_competencia_fuente",
    ),
    "habilidad": (
        "habilidades_fuente.jsonl",
        "id_habilidad_fuente",
        "id_habilidad_canonica",
        "descripcion_fuente",
    ),
    "herramienta": (
        "herramientas_fuente.jsonl",
        "id_herramienta_fuente",
        "id_herramienta_canonica",
        "nombre_herramienta",
    ),
}
_CATALOGS = {
    "competencia": ("catalogo_competencias.csv", "id_competencia", "nombre_competencia"),
    "habilidad": ("catalogo_habilidades.csv", "id_habilidad", "nombre_habilidad"),
    "herramienta": ("catalogo_herramientas.csv", "id_herramienta", "nombre_herramienta"),
}


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
    }
    missing = [key for key in IDENTITY_FIELDS if not identity[key]]
    if missing:
        raise IdentidadFuenteIncompleta(
            "Identidad de paquete CHH incompleta; faltan: " + ", ".join(missing) + "."
        )
    return identity


def clave_fuente_chh(identity: Mapping[str, str]) -> str:
    return json.dumps(
        {key: _text(identity.get(key)) for key in IDENTITY_FIELDS},
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
    return [
        _assemble_one(package_id, rows, fuentes=fuentes, relaciones=relaciones, archivos=archivos)
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
        if skills and not any(
            value[3] in competency_ids and value[4] in skill_ids for value in parsed
        ):
            findings.append(
                _finding(
                    "PAQUETE_HABILIDAD_SIN_RELACION",
                    "Toda habilidad presente debe conservar una relación del paquete.",
                    package_id,
                )
            )
        if tools and not any(value[4] in skill_ids and value[5] in tool_ids for value in parsed):
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
) -> dict[str, object]:
    ordered = sorted((dict(row) for row in rows), key=_row_sort_key)
    identity = _mapping(ordered[0].get(PACKAGE_SOURCE_IDENTITY_FIELD))
    identity_text = {key: _text(identity.get(key)) for key in IDENTITY_FIELDS}
    by_type: dict[str, list[dict[str, object]]] = {key: [] for key in _TYPE_ORDER}
    for row in ordered:
        kind = _text(row.get("tipo")).casefold()
        if kind in by_type:
            by_type[kind].append(_component_from_row(row, kind))
    _add_source_components(by_type, identity, fuentes)
    _add_canonical_components(by_type, identity, fuentes, archivos)
    for kind in by_type:
        by_type[kind] = _unique_components(by_type[kind])
    aliases: list[dict[str, object]] = []
    for row in ordered:
        if not row.get("auto_deduplicated"):
            continue
        evidence = row.get("evidencia")
        aliases.append(
            {
                "id_pendiente": _text(row.get("id_pendiente")),
                "representative_id": _text(
                    row.get("exact_duplicate_representative_id") or row.get("representative_id")
                ),
                "evidence": list(evidence) if isinstance(evidence, list) else [],
                PACKAGE_SOURCE_IDENTITY_FIELD: dict(identity),
            }
        )
    open_rows = [
        row
        for row in ordered
        if not row.get("auto_deduplicated")
        and bool(row.get("requiere_decision", True))
        and not _text(row.get("decision"))
    ]
    decisions = {
        _text(row.get("decision")).upper() for row in ordered if _text(row.get("decision"))
    }
    decision = next(iter(decisions)) if len(decisions) == 1 else "MIXED" if decisions else None
    package_relations = relaciones_para_paquete_chh(
        relaciones or (), identity, fuentes=fuentes, package_id=package_id
    )
    package_relations.sort(key=lambda row: tuple(_text(row.get(key)) for key in RELATION_KEYS))
    components = {
        "competencias": by_type["competencia"],
        "habilidades": by_type["habilidad"],
        "herramientas": by_type["herramienta"],
    }
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
        "source_relationships": package_relations,
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
                for flag in _list_value(row.get("flags"))
                if _text(flag)
            }
        ),
        "requires_human_decision": bool(open_rows),
        "requiere_decision": bool(open_rows),
        "decision": decision,
        "package_decision": decision,
        "decision_state": "PENDING" if open_rows else "MIXED" if decision == "MIXED" else "DECIDED",
    }


def _add_source_components(
    by_type: dict[str, list[dict[str, object]]],
    identity: Mapping[str, object],
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None,
) -> None:
    if not fuentes:
        return
    for kind, (filename, source_id_key, canonical_key, name_key) in _SOURCE_FILES.items():
        for source in fuentes.get(filename, ()):
            if not _scope_matches(source, identity):
                continue
            canonical, name = _text(source.get(canonical_key)), _text(source.get(name_key))
            if canonical or name:
                by_type[kind].append(
                    {
                        "tipo": kind,
                        "id_fuente": _text(source.get(source_id_key)),
                        "id_canonico": canonical,
                        f"id_{kind}": canonical,
                        "nombre": name,
                        "descripcion": _text(
                            source.get("descripcion_fuente") or source.get("texto_evidencia")
                        ),
                        "source_identity": identidad_fuente_chh(source),
                        "source": dict(source),
                        "canonical": bool(canonical),
                    }
                )


def _add_canonical_components(
    by_type: dict[str, list[dict[str, object]]],
    identity: Mapping[str, object],
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None,
    archivos: Mapping[str, Sequence[Mapping[str, object]]] | None,
) -> None:
    if not archivos:
        return
    for relation in archivos.get("cobertura_curricular.csv", ()):
        if not _relation_scope_matches(relation, identity, fuentes):
            continue
        for kind, (filename, id_key, name_key) in _CATALOGS.items():
            identifier = _text(relation.get(id_key))
            if not identifier:
                continue
            catalog_row = next(
                (
                    item
                    for item in archivos.get(filename, ())
                    if _text(item.get(id_key)) == identifier
                ),
                {},
            )
            by_type[kind].append(
                {
                    "tipo": kind,
                    "id_canonico": identifier,
                    id_key: identifier,
                    "nombre": _text(catalog_row.get(name_key)),
                    "descripcion": _text(
                        catalog_row.get("descripcion_breve")
                        or catalog_row.get("descripcion_breve_herramienta")
                        or catalog_row.get("descripcion_breve_competencia")
                    ),
                    "source_identity": dict(identity),
                    "canonical": True,
                }
            )


def _component_from_row(row: Mapping[str, object], kind: str) -> dict[str, object]:
    proposal = _mapping(row.get("propuesta"))
    identifier = _text(proposal.get("id")) or _text(row.get(f"id_{kind}"))
    return {
        "tipo": kind,
        "id_pendiente": _text(row.get("id_pendiente")),
        "id_fuente": _text(row.get("id_habilidad_fuente")),
        "id_canonico": identifier,
        f"id_{kind}": identifier,
        "nombre": _text(proposal.get("nombre") or proposal.get("id")),
        "descripcion": _text(proposal.get("descripcion") or row.get("descripcion_fuente")),
        "estado_resolucion": _text(row.get("estado_resolucion")),
        "decision": _text(row.get("decision")),
        "source_identity": dict(_mapping(row.get(PACKAGE_SOURCE_IDENTITY_FIELD))),
        "row": dict(row),
        "canonical": False,
    }


def _unique_components(values: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    unique: dict[tuple[str, str, str], dict[str, object]] = {}
    for value in values:
        key = (
            _text(value.get("tipo")),
            _text(value.get("id_canonico")),
            _text(value.get("id_pendiente")) or _text(value.get("nombre")).casefold(),
        )
        unique.setdefault(key, dict(value))
    return sorted(
        unique.values(),
        key=lambda item: (
            _TYPE_ORDER.get(_text(item.get("tipo")), 99),
            _text(item.get("nombre")).casefold(),
            _text(item.get("id_canonico")),
            _text(item.get("id_pendiente")),
        ),
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


def _scope_matches(row: Mapping[str, object], identity: Mapping[str, object]) -> bool:
    row_package, expected_package = (
        _first(row, *PACKAGE_ID_ALIASES),
        _first(identity, *PACKAGE_ID_ALIASES),
    )
    if not _identity_complete(identity):
        return False
    if row_package and expected_package and row_package != expected_package:
        return False
    aliases = {
        "id_ejecucion": ("id_ejecucion", "execution_id"),
        "carrera": ("carrera", "career"),
        "periodo": ("periodo", "period"),
        "id_curso": ("id_curso", "course_id"),
        "id_silabo": ("id_silabo", "syllabus_id", "silabo"),
        "id_habilidad_fuente": ("id_habilidad_fuente", "source_skill_id"),
    }
    row_identity = _mapping(row.get(PACKAGE_SOURCE_IDENTITY_FIELD))
    if row_identity:
        return _identity_equal(row_identity, identity)
    return all(_first(row, *keys) == _text(identity.get(key)) for key, keys in aliases.items())


def relaciones_para_paquete_chh(
    relaciones: Sequence[Mapping[str, object]],
    identity: Mapping[str, object],
    *,
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None = None,
    package_id: str = "",
) -> list[dict[str, object]]:
    """Return only relations proven to belong to one complete source package."""

    if not _identity_complete(identity):
        return []
    selected: list[dict[str, object]] = []
    for relation in relaciones:
        if not _relation_scope_matches(relation, identity, fuentes):
            continue
        scoped = dict(relation)
        scoped[PACKAGE_SOURCE_IDENTITY_FIELD] = dict(identity)
        scoped["id_habilidad_fuente"] = _text(identity.get("id_habilidad_fuente"))
        scoped[PACKAGE_ID_FIELD] = package_id or id_paquete_chh(
            {key: _text(identity.get(key)) for key in IDENTITY_FIELDS}
        )
        selected.append(scoped)
    return selected


def _relation_scope_matches(
    relation: Mapping[str, object],
    identity: Mapping[str, object],
    fuentes: Mapping[str, Sequence[Mapping[str, object]]] | None,
) -> bool:
    if _scope_matches(relation, identity):
        return True
    relation_course = _first(relation, "id_curso", "course_id")
    relation_syllabus = _first(relation, "id_silabo", "syllabus_id", "silabo")
    if relation_course != _text(identity.get("id_curso")) or relation_syllabus != _text(
        identity.get("id_silabo")
    ):
        return False
    if not fuentes:
        return False
    source_skill = _text(identity.get("id_habilidad_fuente"))
    scoped_skills = {
        _text(item.get("id_habilidad_canonica"))
        for item in fuentes.get("habilidades_fuente.jsonl", ())
        if _scope_matches(item, identity) and _text(item.get("id_habilidad_canonica"))
    }
    scoped_competencies = {
        _text(item.get("id_competencia_canonica"))
        for item in fuentes.get("competencias_fuente.jsonl", ())
        if _scope_matches(item, identity) and _text(item.get("id_competencia_canonica"))
    }
    scoped_tools = {
        _text(item.get("id_herramienta_canonica"))
        for item in fuentes.get("herramientas_fuente.jsonl", ())
        if _scope_matches(item, identity) and _text(item.get("id_herramienta_canonica"))
    }
    return (
        bool(source_skill)
        and _text(relation.get("id_habilidad")) in scoped_skills
        and _text(relation.get("id_competencia")) in scoped_competencies
        and (
            not _text(relation.get("id_herramienta"))
            or _text(relation.get("id_herramienta")) in scoped_tools
        )
    )


def _identity_complete(identity: Mapping[str, object]) -> bool:
    return all(_text(identity.get(key)) for key in IDENTITY_FIELDS)


def _identity_equal(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    return all(_text(left.get(key)) == _text(right.get(key)) for key in IDENTITY_FIELDS)


def _rows(package: Mapping[str, object]) -> list[Mapping[str, object]]:
    value = package.get("filas") or package.get("legacy_rows")
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _row_sort_key(row: Mapping[str, object]) -> tuple[object, ...]:
    kind, proposal = _text(row.get("tipo")).casefold(), _mapping(row.get("propuesta"))
    return (
        _TYPE_ORDER.get(kind, 99),
        _text(proposal.get("nombre") or proposal.get("id")).casefold(),
        _text(row.get("id_pendiente")),
    )


def _first(mapping: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        if _text(mapping.get(key)):
            return _text(mapping.get(key))
    return ""


def _text(value: object) -> str:
    return str(value or "").strip()


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


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
