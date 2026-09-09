"""Component deduplication, names, and provenance for CHH package projection."""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping, Sequence

PACKAGE_SOURCE_IDENTITY_FIELD = "source_identity"
_TYPE_ORDER = {"competencia": 0, "habilidad": 1, "herramienta": 2}
_UNRESOLVED_RESOLUTION_STATES = {
    "CANONIZADA_CON_PROPUESTA_PERFIL",
    "PENDIENTE",
    "PENDIENTE_CATALOGACION",
    "PENDIENTE_AMPLIACION_PERFIL",
    "REQUIERE_REVISION_HUMANA",
    "MANTENIDA_PENDIENTE",
    "PENDING",
    "REVIEW",
    "REQUIRES_HUMAN_REVIEW",
}
_TECHNICAL_NAME = re.compile(
    r"^(?:HAB|COMP|HERR|PROP|PROPOSAL|PEN|PKG)(?:[_-][A-Za-z0-9:-]+)+$",
    re.IGNORECASE,
)
_HASH_NAME = re.compile(r"^(?:sha256:)?[0-9a-f]{16,}$", re.IGNORECASE)


def _unique_components(values: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    canonical_ids = {
        (_text(value.get("tipo")), _component_identifier(value))
        for value in values
        if value.get("canonical") and _component_identifier(value)
    }
    canonical_names = {
        (_text(value.get("tipo")), _normalized_name(_component_name(value)))
        for value in values
        if value.get("canonical") and _component_name(value)
    }
    canonical_source_counts = Counter(
        source_key
        for value in values
        if value.get("canonical") and (source_key := _component_source_key(value)) is not None
    )
    unique: dict[tuple[str, str, str], dict[str, object]] = {}
    for value in values:
        item = dict(value)
        key = _component_key(item, canonical_ids, canonical_names)
        source_key = _component_source_key(item)
        if item.get("canonical") and source_key and canonical_source_counts[source_key] == 1:
            pending_matches = [
                existing_key
                for existing_key, existing in unique.items()
                if (
                    not existing.get("canonical")
                    and not _is_provisional_component(existing)
                    and _has_structured_proposal(existing)
                    and _component_source_key(existing) == source_key
                )
            ]
            if len(pending_matches) == 1:
                unique[pending_matches[0]] = _merge_components(unique[pending_matches[0]], item)
                continue
        if (
            key not in unique
            and not item.get("canonical")
            and not _is_provisional_component(item)
            and _has_structured_proposal(item)
        ):
            canonical_matches = [
                existing_key
                for existing_key, existing in unique.items()
                if existing.get("canonical")
                and source_key
                and _component_source_key(existing) == source_key
            ]
            if len(canonical_matches) == 1:
                key = canonical_matches[0]
        if key in unique:
            unique[key] = _merge_components(unique[key], item)
        else:
            unique[key] = _with_component_provenance(item)
    return sorted(
        unique.values(),
        key=lambda item: (
            _TYPE_ORDER.get(_text(item.get("tipo")), 99),
            _text(item.get("nombre")).casefold(),
            _text(item.get("id_canonico")),
            _text(item.get("id_pendiente")),
        ),
    )


def _component_identifier(value: Mapping[str, object]) -> str:
    kind = _text(value.get("tipo"))
    return _text(value.get(f"id_{kind}") or value.get("id_canonico"))


def _component_name(value: Mapping[str, object]) -> str:
    description = _text(value.get("descripcion"))
    candidates = [value.get("nombre"), value.get("nombre_propuesto")]
    if _text(value.get("tipo")).casefold() != "habilidad":
        candidates.append(value.get("nombre_fuente"))
    return next(
        (
            name
            for candidate in candidates
            if (
                name := _usable_display_name(
                    candidate,
                    description=description,
                    trusted_tool_name=(
                        _text(value.get("tipo")).casefold() == "herramienta"
                        and bool(value.get("canonical") or value.get("source"))
                    ),
                )
            )
        ),
        "",
    )


def _component_key(
    value: Mapping[str, object],
    canonical_ids: set[tuple[str, str]],
    canonical_names: set[tuple[str, str]],
) -> tuple[str, str, str]:
    kind = _text(value.get("tipo"))
    identifier = _component_identifier(value)
    if identifier and (value.get("canonical") or (kind, identifier) in canonical_ids):
        return ("canonical", kind, identifier)
    name = _component_name(value)
    normalized = _normalized_name(name)
    if normalized:
        return ("name", kind, normalized)
    source_identity = json.dumps(
        _mapping(value.get(PACKAGE_SOURCE_IDENTITY_FIELD)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (
        "source",
        kind,
        "|".join(
            (
                source_identity,
                _text(value.get("id_fuente")),
                _text(value.get("id_pendiente")),
            )
        ),
    )


def _component_source_key(value: Mapping[str, object]) -> tuple[str, str, str] | None:
    source_id = _text(value.get("id_fuente"))
    if not source_id:
        return None
    identity = json.dumps(
        _mapping(value.get(PACKAGE_SOURCE_IDENTITY_FIELD)),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return (_text(value.get("tipo")), identity, source_id)


def _has_structured_proposal(value: Mapping[str, object]) -> bool:
    proposal = _mapping(value.get("propuesta"))
    return bool(_text(proposal.get("nombre") or proposal.get("id")))


def _is_provisional_component(value: Mapping[str, object]) -> bool:
    return (
        bool(_text(value.get("id_canonico_propuesto")))
        or _text(value.get("estado_resolucion")).upper() in _UNRESOLVED_RESOLUTION_STATES
    )


def _with_component_provenance(value: Mapping[str, object]) -> dict[str, object]:
    result = dict(value)
    result["provenance"] = [_component_provenance(value)]
    return result


def _component_provenance(value: Mapping[str, object]) -> dict[str, object]:
    return {
        field: value[field]
        for field in (
            "id_pendiente",
            "id_fuente",
            "id_canonico",
            "id_canonico_propuesto",
            "nombre_propuesto",
            "propuesta",
            "source_identity",
            "source",
            "row",
        )
        if field in value and value[field]
    }


def _merge_components(
    first: Mapping[str, object], second: Mapping[str, object]
) -> dict[str, object]:
    result = dict(first)
    provenance = [
        item
        for item in (_list_value(first.get("provenance")) + [_component_provenance(second)])
        if isinstance(item, Mapping) and item
    ]
    unique_provenance: list[dict[str, object]] = []
    for item in provenance:
        if dict(item) not in unique_provenance:
            unique_provenance.append(dict(item))
    result["provenance"] = unique_provenance

    for field, singular in (
        ("id_pendientes", "id_pendiente"),
        ("id_fuentes", "id_fuente"),
        ("source_identities", "source_identity"),
        ("propuestas", "propuesta"),
    ):
        values: list[object] = []
        for item in (first, second):
            existing = item.get(field)
            field_values: list[object] = (
                list(existing) if isinstance(existing, list) else [item.get(singular)]
            )
            for candidate in field_values:
                if candidate and candidate not in values:
                    values.append(candidate)
        if values:
            result[field] = values

    proposed_names: list[str] = []
    for item in (first, second):
        name = _usable_display_name(
            item.get("nombre_propuesto"), description=_text(item.get("descripcion"))
        )
        if name and name not in proposed_names:
            proposed_names.append(name)
    if proposed_names:
        result["nombre_propuesto"] = proposed_names[0]
        result["nombres_propuestos"] = proposed_names

    candidates: list[tuple[int, str]] = []
    for item in (first, second):
        name = _component_name(item)
        if not name:
            continue
        if item.get("canonical") and _usable_display_name(
            item.get("nombre"),
            description=_text(item.get("descripcion")),
            trusted_tool_name=(
                _text(item.get("tipo")).casefold() == "herramienta"
                and bool(item.get("canonical") or item.get("source"))
            ),
        ):
            rank = 3
        elif _usable_display_name(
            item.get("nombre_propuesto"), description=_text(item.get("descripcion"))
        ):
            rank = 2
        else:
            rank = 1
        candidates.append((rank, name))
    display_name = ""
    if candidates:
        display_name = max(candidates, key=lambda candidate: candidate[0])[1]
    result["nombre"] = display_name
    result["display_name"] = display_name
    result["estado_nombre"] = "" if display_name else "PENDIENTE_CATALOGACION"
    result["canonical"] = bool(first.get("canonical") or second.get("canonical"))
    if result["canonical"] and _component_identifier(second) and second.get("canonical"):
        kind = _text(second.get("tipo"))
        result["id_canonico"] = _component_identifier(second)
        result[f"id_{kind}"] = _component_identifier(second)
    return result


def _normalized_name(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", _text(value))
    without_accents = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    return re.sub(r"[^a-z0-9]+", " ", without_accents.casefold()).strip()


def _usable_display_name(
    value: object,
    *,
    description: str = "",
    trusted_tool_name: bool = False,
) -> str:
    name = _text(value)
    if not name or _TECHNICAL_NAME.fullmatch(name) or _HASH_NAME.fullmatch(name):
        return ""
    if (
        not trusted_tool_name
        and description
        and _normalized_name(name) == _normalized_name(description)
    ):
        return ""
    return name


def _text(value: object) -> str:
    return str(value or "").strip()


def _mapping(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, Mapping) else {}


def _list_value(value: object) -> list[object]:
    return list(value) if isinstance(value, list) else []
