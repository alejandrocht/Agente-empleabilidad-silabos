"""Closed catalog resolution for the isolated LangExtract diagnostic runner."""

from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

_CATALOGS = {
    "competencia": (
        "catalogo_competencias.csv",
        "id_competencia",
        "nombre_competencia",
        (
            "id_competencia",
            "nombre_competencia",
            "descripcion_breve_competencia",
            "tipo_competencia",
        ),
    ),
    "habilidad": (
        "catalogo_habilidades.csv",
        "id_habilidad",
        "nombre_habilidad",
        ("id_habilidad", "nombre_habilidad", "descripcion_breve"),
    ),
    "herramienta": (
        "catalogo_herramientas.csv",
        "id_herramienta",
        "nombre_herramienta",
        ("id_herramienta", "nombre_herramienta", "descripcion_breve_herramienta"),
    ),
}
_PRIMARY_START = re.compile(r"\[PRIMARY EVIDENCE:.*?\]\n", re.IGNORECASE)
_COMPLEMENTARY_START = re.compile(r"\n\n\[COMPLEMENTARY CONTEXT:", re.IGNORECASE)
_SYLLABUS_METADATA = {
    "career": (
        re.compile(r"(?im)^\s*(?:carrera|career)\s*:\s*(.+?)\s*$"),
        re.compile(r"(?im)^\s*carrera\s+de\s+(.+?)\s*$"),
    ),
    "period": (
        re.compile(r"(?im)^\s*(?:periodo|per[ií]odo|period)\s*:\s*(.+?)\s*$"),
        re.compile(r"(?im)^\s*s[ií]labo\s+(\d{4}-\d+)\s*$"),
    ),
}


@dataclass(frozen=True, slots=True)
class CatalogSelection:
    directory: Path
    career: str
    period: str
    version: str


@dataclass(frozen=True, slots=True)
class _Term:
    identifier: str
    name: str


class _CatalogError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class CatalogPreflightError(ValueError):
    """Raised before extraction when the selected immutable catalog is unusable."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _Catalog:
    def __init__(
        self,
        selection: CatalogSelection,
        terms: Mapping[str, tuple[_Term, ...]],
        aliases: Mapping[str, Mapping[str, _Term]],
        alias_literals: Mapping[str, tuple[str, ...]],
    ) -> None:
        self.selection = selection
        self.terms = terms
        self.aliases = aliases
        self.alias_literals = alias_literals
        self._by_name = {
            kind: {_key(term.name): term for term in catalog_terms}
            for kind, catalog_terms in terms.items()
        }

    def resolve(self, kind: str, proposal: str) -> tuple[_Term | None, str | None]:
        key = _key(proposal)
        if not key:
            return None, "CATALOGO_PROPUESTA_VACIA"
        term = self._by_name[kind].get(key)
        if term is not None:
            return term, None
        term = self.aliases[kind].get(key)
        if term is not None:
            return term, None
        return None, _missing_code(kind)


def resolve_catalog_document(
    catalog: _Catalog,
    reasoned_text: str,
    syllabus_text: str,
    packages: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    """Return canonical diagnostic fields without changing the raw LangExtract output."""

    metadata = _syllabus_metadata(syllabus_text)
    if not _metadata_matches(metadata, catalog.selection):
        return _pending_document(packages, "CATALOGO_METADATA_NO_COINCIDE", catalog.selection)

    serialized_packages = [_resolve_package(catalog, package) for package in packages]
    unlinked = _resolve_tools(catalog, reasoned_text, packages, serialized_packages)
    return {
        "catalogo": {
            "estado": "RESUELTO",
            "career": catalog.selection.career,
            "period": catalog.selection.period,
            "version": catalog.selection.version,
        },
        "paquetes": serialized_packages,
        "herramientas_sin_vinculo": unlinked,
    }


def preflight_catalog(selection: CatalogSelection) -> _Catalog:
    """Load the selected catalog once, before a document can reach the extractor."""
    try:
        return _load_catalog(selection)
    except _CatalogError as error:
        raise CatalogPreflightError(error.code) from error


def _load_catalog(selection: CatalogSelection) -> _Catalog:
    if not all(_key(value) for value in (selection.career, selection.period, selection.version)):
        raise _CatalogError("CATALOGO_SELECCION_INVALIDA")
    metadata_path = selection.directory / "catalogo_metadata.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise _CatalogError("CATALOGO_METADATA_INVALIDA") from error
    if not isinstance(metadata, dict) or not _selection_matches_metadata(selection, metadata):
        raise _CatalogError("CATALOGO_SELECCION_NO_COINCIDE")

    terms = {kind: _load_terms(selection.directory, kind) for kind in _CATALOGS}
    aliases, alias_literals = _load_aliases(metadata, terms)
    return _Catalog(selection, terms, aliases, alias_literals)


def _load_terms(directory: Path, kind: str) -> tuple[_Term, ...]:
    filename, identifier_column, name_column, headers = _CATALOGS[kind]
    try:
        with (directory / filename).open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if tuple(reader.fieldnames or ()) != headers:
                raise _CatalogError("CATALOGO_CSV_INVALIDO")
            terms = tuple(
                _Term(row.get(identifier_column, "").strip(), row.get(name_column, "").strip())
                for row in reader
            )
    except OSError as error:
        raise _CatalogError("CATALOGO_CSV_INVALIDO") from error
    if not terms or any(not term.identifier or not _key(term.name) for term in terms):
        raise _CatalogError("CATALOGO_CSV_INVALIDO")
    if len({term.identifier for term in terms}) != len(terms):
        raise _CatalogError("CATALOGO_IDENTIFICADOR_DUPLICADO")
    if len({_key(term.name) for term in terms}) != len(terms):
        raise _CatalogError("CATALOGO_NOMBRE_AMBIGUO")
    return terms


def _load_aliases(
    metadata: Mapping[str, object], terms: Mapping[str, tuple[_Term, ...]]
) -> tuple[dict[str, dict[str, _Term]], dict[str, tuple[str, ...]]]:
    raw_aliases = metadata.get("aliases", {})
    if not isinstance(raw_aliases, dict):
        raise _CatalogError("CATALOGO_ALIASES_INVALIDOS")
    resolved: dict[str, dict[str, _Term]] = {kind: {} for kind in _CATALOGS}
    literals: dict[str, list[str]] = {kind: [] for kind in _CATALOGS}
    for kind, aliases in raw_aliases.items():
        if kind not in _CATALOGS or not isinstance(aliases, dict):
            raise _CatalogError("CATALOGO_ALIASES_INVALIDOS")
        canonical = {_key(term.name): term for term in terms[kind]}
        for alias, target in aliases.items():
            if not isinstance(alias, str) or not isinstance(target, str):
                raise _CatalogError("CATALOGO_ALIASES_INVALIDOS")
            alias_key = _key(alias)
            target_term = canonical.get(_key(target))
            if not alias_key or target_term is None or alias_key in resolved[kind]:
                raise _CatalogError("CATALOGO_ALIASES_INVALIDOS")
            resolved[kind][alias_key] = target_term
            literals[kind].append(alias)
    return resolved, {kind: tuple(values) for kind, values in literals.items()}


def _selection_matches_metadata(
    selection: CatalogSelection, metadata: Mapping[str, object]
) -> bool:
    provenance = metadata.get("provenance")
    return (
        isinstance(provenance, str)
        and bool(provenance.strip())
        and all(
            isinstance(metadata.get(field), str) and _key(str(metadata[field])) == _key(value)
            for field, value in (
                ("career", selection.career),
                ("period", selection.period),
                ("version", selection.version),
            )
        )
    )


def _syllabus_metadata(source_text: str) -> dict[str, str | None]:
    return {
        field: next(
            (
                match.group(1).strip()
                for pattern in patterns
                if (match := pattern.search(source_text))
            ),
            None,
        )
        for field, patterns in _SYLLABUS_METADATA.items()
    }


def _metadata_matches(metadata: Mapping[str, str | None], selection: CatalogSelection) -> bool:
    return all(
        metadata.get(field) is not None and _key(str(metadata[field])) == _key(value)
        for field, value in (("career", selection.career), ("period", selection.period))
    )


def _resolve_package(catalog: _Catalog, package: Mapping[str, object]) -> dict[str, object]:
    result = dict(package)
    result["catalogo"] = {
        "habilidad": _resolution(catalog, "habilidad", package.get("habilidad_propuesta")),
        "competencia": _resolution(catalog, "competencia", package.get("competencia_propuesta")),
        "herramientas_vinculadas": [],
    }
    return result


def _resolution(catalog: _Catalog, kind: str, value: object) -> dict[str, object]:
    proposal = value if isinstance(value, str) else ""
    term, code = catalog.resolve(kind, proposal)
    return {
        "propuesta": proposal or None,
        "estado": "RESUELTO" if term is not None else "PENDIENTE",
        "codigo": code,
        "id": term.identifier if term is not None else None,
    }


def _resolve_tools(
    catalog: _Catalog,
    source_text: str,
    raw_packages: Sequence[Mapping[str, object]],
    packages: Sequence[dict[str, object]],
) -> list[dict[str, object]]:
    mentions = _tool_mentions(catalog, source_text, raw_packages)
    unlinked: list[dict[str, object]] = []
    for mention, start, end in mentions:
        attached = False
        for raw_package, package in zip(raw_packages, packages, strict=True):
            if not _tool_explicitly_associated(raw_package, mention, start, end):
                continue
            catalog_data = package["catalogo"]
            if not isinstance(catalog_data, dict):
                continue
            linked = catalog_data["herramientas_vinculadas"]
            if isinstance(linked, list) and mention not in linked:
                linked.append(mention)
            attached = True
        if not attached and mention not in unlinked:
            unlinked.append(mention)
    return unlinked


def _tool_mentions(
    catalog: _Catalog,
    source_text: str,
    packages: Sequence[Mapping[str, object]],
) -> list[tuple[dict[str, object], int, int]]:
    candidates = [term.name for term in catalog.terms["herramienta"]]
    candidates.extend(catalog.alias_literals["herramienta"])
    candidates.extend(_raw_tools(packages))
    mentions: list[tuple[int, dict[str, object], int, int]] = []
    seen: set[tuple[int, int, str]] = set()
    for candidate in dict.fromkeys(candidates):
        term, code = catalog.resolve("herramienta", candidate)
        for start, end, literal in _literal_matches(source_text, candidate):
            key = (start, end, term.identifier if term is not None else _key(candidate))
            if key in seen:
                continue
            seen.add(key)
            mentions.append(
                (
                    start,
                    {
                        "propuesta": candidate,
                        "evidencia_literal": literal,
                        "estado": "RESUELTO" if term is not None else "PENDIENTE",
                        "codigo": code,
                        "id": term.identifier if term is not None else None,
                    },
                    start,
                    end,
                )
            )
    return [
        (mention, start, end)
        for _, mention, start, end in sorted(mentions, key=lambda item: item[0])
    ]


def _raw_tools(packages: Sequence[Mapping[str, object]]) -> list[str]:
    tools: list[str] = []
    for package in packages:
        value = package.get("herramientas", [])
        if isinstance(value, list):
            tools.extend(tool for tool in value if isinstance(tool, str) and tool.strip())
    return tools


def _literal_matches(source_text: str, candidate: str) -> list[tuple[int, int, str]]:
    if not candidate.strip():
        return []
    pattern = re.compile(rf"(?<!\w){re.escape(candidate)}(?!\w|\.\w)", re.IGNORECASE)
    return [
        (match.start(), match.end(), match.group())
        for match in pattern.finditer(source_text)
        if _in_primary_evidence(match.start(), source_text)
    ]


def _in_primary_evidence(position: int, source_text: str) -> bool:
    primary = _PRIMARY_START.search(source_text)
    if primary is None:
        return False
    end_match = _COMPLEMENTARY_START.search(source_text, primary.end())
    primary_end = end_match.start() if end_match is not None else len(source_text)
    return primary.end() <= position < primary_end


def _tool_explicitly_associated(
    package: Mapping[str, object], mention: Mapping[str, object], start: int, end: int
) -> bool:
    tools = package.get("herramientas")
    proposal = mention.get("propuesta")
    if not isinstance(tools, list) or not isinstance(proposal, str):
        return False
    if not any(isinstance(tool, str) and _key(tool) == _key(proposal) for tool in tools):
        return False
    evidence = package.get("evidencia_principal")
    if not isinstance(evidence, Mapping):
        return False
    evidence_start = evidence.get("start_pos")
    evidence_end = evidence.get("end_pos")
    return (
        isinstance(evidence_start, int)
        and isinstance(evidence_end, int)
        and start < evidence_end
        and evidence_start < end
    )


def _pending_document(
    packages: Sequence[Mapping[str, object]], code: str, selection: CatalogSelection
) -> dict[str, object]:
    resolved = []
    for package in packages:
        result = dict(package)
        catalog_data: dict[str, object] = {
            kind: {
                "propuesta": package.get(f"{kind}_propuesta"),
                "estado": "PENDIENTE",
                "codigo": code,
                "id": None,
            }
            for kind in ("habilidad", "competencia")
        }
        catalog_data["herramientas_vinculadas"] = []
        result["catalogo"] = catalog_data
        resolved.append(result)
    return {
        "catalogo": {
            "estado": "PENDIENTE",
            "codigo": code,
            "career": selection.career,
            "period": selection.period,
            "version": selection.version,
        },
        "paquetes": resolved,
        "paquetes_crudos": [dict(package) for package in packages],
        "herramientas_sin_vinculo": [],
    }


def _missing_code(kind: str) -> str:
    return {
        "competencia": "COMPETENCIA_CATALOGO_NO_ENCONTRADA",
        "habilidad": "HABILIDAD_CATALOGO_NO_ENCONTRADA",
        "herramienta": "HERRAMIENTA_CATALOGO_NO_ENCONTRADA",
    }[kind]


def _key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(re.sub(r"[^\w]+", " ", without_accents.casefold()).split())
