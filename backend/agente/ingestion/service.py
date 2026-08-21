"""Bounded, offline document-to-graph ingestion for CIAR.

This module is intentionally not imported by the request graph or API routes.
The only production write adapter uses the dedicated ``NEO4J_INGEST_*``
credential group and the parameterized ``Neo4jGraph.add_graph_documents`` API.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

from langchain_core.documents import Document
from langchain_neo4j.graphs.graph_document import GraphDocument, Node, Relationship

MAX_DOCUMENT_ID_CHARS = 128
MAX_PROPERTY_CHARS = 2_000
MAX_NODE_ID_CHARS = 256
MAX_SOURCE_BYTES = 256_000

ALLOWED_NODE_TYPES = frozenset(
    {
        "Carrera",
        "Curso",
        "Facultad",
        "Empresa",
        "Industria",
        "Oferta_Laboral",
        "Puesto",
        "Habilidad",
        "Herramienta",
        "Competencia",
        "Requerimiento_Laboral",
        "Cobertura_Curricular",
    }
)
ALLOWED_RELATIONSHIP_TYPES = frozenset(
    {"ENSENIA", "TIENE", "DIRIGE_A", "PUBLICA", "AGRUPA", "OFRECE", "DEFIINE", "REQUIERE"}
)

ALLOWED_NODE_PROPERTIES: Mapping[str, frozenset[str]] = {
    "Carrera": frozenset({"id_carrera", "nombre_carrera", "descripcion", "facultad_id"}),
    "Curso": frozenset({"id_curso", "nombre_curso", "descripcion", "creditos", "nivel"}),
    "Facultad": frozenset({"id_facultad", "nombre_facultad", "descripcion"}),
    "Empresa": frozenset({"id_empresa", "nombre", "razon_social", "descripcion"}),
    "Industria": frozenset({"id_industria", "nombre", "sector_macro", "descripcion"}),
    "Oferta_Laboral": frozenset(
        {
            "id_ofe_laboral",
            "cargo",
            "area",
            "area_especifica",
            "descripcion_breve",
            "fecha_publicacion",
            "fecha_finalizacion",
        }
    ),
    "Puesto": frozenset({"id_puesto", "nombre", "descripcion"}),
    "Habilidad": frozenset({"id_habilidad", "nombre_habilidad", "descripcion"}),
    "Herramienta": frozenset({"id_herramienta", "nombre_herramienta", "descripcion"}),
    "Competencia": frozenset({"id_competencia", "nombre_competencia", "descripcion"}),
    "Requerimiento_Laboral": frozenset({"id_requerimiento_laboral", "nombre", "descripcion"}),
    "Cobertura_Curricular": frozenset({"id_cobertura_curricular", "nombre", "descripcion"}),
}
ALLOWED_RELATIONSHIP_PROPERTIES = frozenset({"nivel", "tipo", "peso", "descripcion"})

_ID_PROPERTY_BY_TYPE = {
    "Carrera": ("id_carrera", "CAR_"),
    "Curso": ("id_curso", "CUR_"),
    "Facultad": ("id_facultad", "FAC_"),
    "Empresa": ("id_empresa", "EMP_"),
    "Industria": ("id_industria", "INDU_"),
    "Oferta_Laboral": ("id_ofe_laboral", "OFE_"),
    "Puesto": ("id_puesto", "PUE_"),
    "Habilidad": ("id_habilidad", "HAB_"),
    "Herramienta": ("id_herramienta", "HER_"),
    "Competencia": ("id_competencia", "COM_"),
    "Requerimiento_Laboral": ("id_requerimiento_laboral", "REQ_"),
    "Cobertura_Curricular": ("id_cobertura_curricular", "COB_"),
}
_SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}\Z")
# Newline, carriage return, and tab are valid in bounded Markdown/text sources.
_CONTROL_CHARACTER = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SECRET = re.compile(
    r"(?i)\b(?:password|passcode|secret|token|api[-_ ]?key|authorization|cookie)\b"
    r"\s*[:=]\s*[^\s,;]+"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_UNSAFE_SOURCE = re.compile(
    r"(?ims)(?:^\s*(?:match|create|merge)\s+[^\n]*(?:\(|\{|\[)|"
    r"^\s*call\s+(?:db\.|[a-z_][a-z0-9_]*\.)|"
    r"^\s*(?:return|with)\s+[a-z_][a-z0-9_`]*(?:\s*[.=]|\s*$)|"
    r"^\s*(?:unwind|delete)\s+[a-z_][a-z0-9_`]*(?:\s|$)|"
    r"^\s*set\s+[a-z_][a-z0-9_`]*\s*[.=]|"
    r"\b(?:match|create|merge)\s*\(|<\s*(?:system|developer|assistant)\s*>|"
    r"(?:system|developer)\s+(?:prompt|message)|ignore\s+(?:all\s+)?previous\s+instructions|"
    r"hidden\s+(?:context|state))"
)


class IngestionError(RuntimeError):
    """Base error for fail-closed ingestion validation and authorization."""


class IngestionAuthorizationError(IngestionError):
    """Raised when an explicit, separately authorized write is unavailable."""


class IngestionValidationError(IngestionError):
    """Raised when source or model output violates the ingestion contract."""


@dataclass(frozen=True, slots=True)
class SourceDocument:
    """One bounded local source document accepted by the admin path."""

    document_id: str
    text: str
    source_name: str


@dataclass(frozen=True, slots=True)
class IngestionLimits:
    """Hard limits applied before model invocation and before each write batch."""

    max_documents: int = 32
    max_document_chars: int = 12_000
    max_nodes_per_document: int = 128
    max_relationships_per_document: int = 256
    batch_size: int = 8

    def __post_init__(self) -> None:
        for name in (
            "max_documents",
            "max_document_chars",
            "max_nodes_per_document",
            "max_relationships_per_document",
            "batch_size",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True, slots=True)
class IngestionCredentials:
    uri: str
    user: str
    password: str
    database: str


@dataclass(frozen=True, slots=True)
class IngestionResult:
    graph_documents: tuple[GraphDocument, ...]
    document_count: int
    written: bool

    @property
    def graph_document_count(self) -> int:
        return len(self.graph_documents)

    def preview(self) -> dict[str, Any]:
        """Return an audit-friendly preview without source text or credentials."""
        return {
            "documents": [
                {
                    "source_id": document.source.id if document.source is not None else None,
                    "nodes": [
                        {
                            "id": node.id,
                            "type": node.type,
                            "properties": dict(node.properties),
                        }
                        for node in document.nodes
                    ],
                    "relationships": [
                        {
                            "source": relationship.source.id,
                            "type": relationship.type,
                            "target": relationship.target.id,
                            "properties": dict(relationship.properties),
                        }
                        for relationship in document.relationships
                    ],
                }
                for document in self.graph_documents
            ],
            "document_count": self.document_count,
            "graph_document_count": self.graph_document_count,
            "written": self.written,
        }


class GraphTransformerLike(Protocol):
    def convert_to_graph_documents(
        self, documents: Sequence[Document], config: object | None = None
    ) -> Sequence[object]: ...


class GraphDocumentWriter(Protocol):
    def write(self, graph_documents: list[GraphDocument]) -> None: ...


def select_ingestion_credentials(
    environ: Mapping[str, str],
) -> IngestionCredentials | None:
    """Select only the complete, dedicated ingestion credential group."""
    names = tuple(f"NEO4J_INGEST_{suffix}" for suffix in ("URI", "USER", "PASSWORD", "DATABASE"))
    values = tuple(environ.get(name, "").strip() for name in names)
    if not any(values):
        return None
    if not all(values):
        raise IngestionAuthorizationError(
            "NEO4J_INGEST_URI, USER, PASSWORD, and DATABASE must be configured together"
        )
    uri, user, password, database = values
    return IngestionCredentials(uri, user, password, database)


def build_llm_graph_transformer(llm: Any) -> Any:
    """Build the schema-constrained transformer used by the offline CLI."""
    from langchain_neo4j import LLMGraphTransformer

    return LLMGraphTransformer(
        llm=llm,
        allowed_nodes=sorted(ALLOWED_NODE_TYPES),
        allowed_relationships=sorted(ALLOWED_RELATIONSHIP_TYPES),
        strict_mode=True,
        node_properties=sorted(
            {
                property_name
                for values in ALLOWED_NODE_PROPERTIES.values()
                for property_name in values
            }
        ),
        relationship_properties=sorted(ALLOWED_RELATIONSHIP_PROPERTIES),
    )


def _safe_text(value: object, *, max_chars: int, field: str) -> str:
    if not isinstance(value, str):
        raise IngestionValidationError(f"{field} must be text")
    normalized = value.strip()
    if not normalized:
        raise IngestionValidationError(f"{field} must be nonblank")
    if len(normalized) > max_chars:
        raise IngestionValidationError(f"{field} exceeds max_chars={max_chars}")
    if (
        _CONTROL_CHARACTER.search(normalized)
        or _SECRET.search(normalized)
        or _BEARER.search(normalized)
    ):
        raise IngestionValidationError(f"{field} contains credentials or control characters")
    if _UNSAFE_SOURCE.search(normalized):
        raise IngestionValidationError(f"{field} contains Cypher or prompt instructions")
    return normalized


def _safe_document_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IngestionValidationError("document_id must be nonblank text")
    normalized = value.strip()
    if len(normalized) > MAX_DOCUMENT_ID_CHARS or _SAFE_ID.fullmatch(normalized) is None:
        raise IngestionValidationError("document_id is not a bounded safe identifier")
    return normalized


def _validate_sources(
    sources: Sequence[SourceDocument], limits: IngestionLimits
) -> list[SourceDocument]:
    if len(sources) > limits.max_documents:
        raise IngestionValidationError(f"source count exceeds max_documents={limits.max_documents}")
    validated: list[SourceDocument] = []
    seen_ids: set[str] = set()
    for source in sources:
        document_id = _safe_document_id(source.document_id)
        if document_id in seen_ids:
            raise IngestionValidationError(f"duplicate document_id: {document_id}")
        seen_ids.add(document_id)
        validated.append(
            SourceDocument(
                document_id=document_id,
                text=_safe_text(
                    source.text, max_chars=limits.max_document_chars, field="source text"
                ),
                source_name=_safe_text(source.source_name, max_chars=256, field="source_name"),
            )
        )
    return validated


def _source_as_document(source: SourceDocument) -> Document:
    return Document(
        page_content=source.text,
        id=source.document_id,
        metadata={"document_id": source.document_id, "source_name": source.source_name},
    )


def _scalar_property(value: object) -> object:
    if value is None or isinstance(value, (bool, int, str)):
        if isinstance(value, str):
            return _safe_text(value, max_chars=MAX_PROPERTY_CHARS, field="property value")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise IngestionValidationError("property value must be finite")
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if len(value) > 32:
            raise IngestionValidationError("property list is too large")
        return [_scalar_property(item) for item in value]
    raise IngestionValidationError("property value has an unsupported type")


def _canonical_node_id(node_type: str, raw_id: object, properties: Mapping[str, object]) -> str:
    id_property, prefix = _ID_PROPERTY_BY_TYPE[node_type]
    candidates = (properties.get(id_property), raw_id)
    for candidate in candidates:
        if (
            isinstance(candidate, str)
            and _SAFE_ID.fullmatch(candidate)
            and candidate.startswith(prefix)
        ):
            return candidate
    if isinstance(raw_id, bool) or not isinstance(raw_id, (str, int)):
        raise IngestionValidationError("node id must be bounded text or integer")
    raw_text = str(raw_id).strip()
    if not raw_text or len(raw_text) > MAX_NODE_ID_CHARS or _CONTROL_CHARACTER.search(raw_text):
        raise IngestionValidationError("node id is not bounded")
    digest = hashlib.sha256(f"{node_type}|{raw_text.casefold()}".encode()).hexdigest()[:24]
    return f"{prefix}{digest}"


def _graph_source(
    raw_graph: object, source: SourceDocument, source_by_id: Mapping[str, SourceDocument]
) -> SourceDocument:
    raw_source = getattr(raw_graph, "source", None)
    raw_id = getattr(raw_source, "id", None)
    metadata = getattr(raw_source, "metadata", {})
    candidate = raw_id or (metadata.get("document_id") if isinstance(metadata, Mapping) else None)
    if isinstance(candidate, str) and candidate in source_by_id:
        return source_by_id[candidate]
    return source


def _normalize_graph_document(
    raw_graph: object,
    source: SourceDocument,
    limits: IngestionLimits,
    source_by_id: Mapping[str, SourceDocument],
) -> GraphDocument:
    raw_nodes = getattr(raw_graph, "nodes", None)
    raw_relationships = getattr(raw_graph, "relationships", None)
    if not isinstance(raw_nodes, Sequence) or isinstance(raw_nodes, (str, bytes, bytearray)):
        raise IngestionValidationError("transformer output must contain nodes")
    if not isinstance(raw_relationships, Sequence) or isinstance(
        raw_relationships, (str, bytes, bytearray)
    ):
        raise IngestionValidationError("transformer output must contain relationships")
    if len(raw_nodes) > limits.max_nodes_per_document:
        raise IngestionValidationError(
            f"node count exceeds max_nodes_per_document={limits.max_nodes_per_document}"
        )
    if len(raw_relationships) > limits.max_relationships_per_document:
        raise IngestionValidationError(
            "relationship count exceeds "
            f"max_relationships_per_document={limits.max_relationships_per_document}"
        )

    normalized_nodes: list[Node] = []
    node_lookup: dict[tuple[str, str], Node] = {}
    object_lookup: dict[int, Node] = {}
    for raw_node in raw_nodes:
        node_type = getattr(raw_node, "type", None)
        if not isinstance(node_type, str) or node_type not in ALLOWED_NODE_TYPES:
            raise IngestionValidationError(f"unsupported node label: {node_type!r}")
        raw_properties = getattr(raw_node, "properties", {})
        if not isinstance(raw_properties, Mapping):
            raise IngestionValidationError("node properties must be a mapping")
        properties: dict[str, object] = {}
        for key, value in raw_properties.items():
            property_key = str(key)
            if property_key in ALLOWED_NODE_PROPERTIES[node_type]:
                properties[property_key] = _scalar_property(value)
        node_id = _canonical_node_id(
            node_type, getattr(raw_node, "id", None), properties
        )
        id_property = _ID_PROPERTY_BY_TYPE[node_type][0]
        properties[id_property] = node_id
        node = Node(id=node_id, type=node_type, properties=properties)
        key = (node_type, str(getattr(raw_node, "id", "")))
        if key not in node_lookup:
            node_lookup[key] = node
            normalized_nodes.append(node)
        object_lookup[id(raw_node)] = node_lookup[key]

    normalized_relationships: list[Relationship] = []
    seen_relationships: set[tuple[str, str, str]] = set()
    for raw_relationship in raw_relationships:
        relationship_type = getattr(raw_relationship, "type", None)
        if (
            not isinstance(relationship_type, str)
            or relationship_type not in ALLOWED_RELATIONSHIP_TYPES
        ):
            raise IngestionValidationError(f"unsupported relationship type: {relationship_type!r}")
        raw_source = getattr(raw_relationship, "source", None)
        raw_target = getattr(raw_relationship, "target", None)
        relationship_source = object_lookup.get(id(raw_source))
        relationship_target = object_lookup.get(id(raw_target))
        if relationship_source is None or relationship_target is None:
            source_key = (str(getattr(raw_source, "type", "")), str(getattr(raw_source, "id", "")))
            target_key = (str(getattr(raw_target, "type", "")), str(getattr(raw_target, "id", "")))
            relationship_source = node_lookup.get(source_key)
            relationship_target = node_lookup.get(target_key)
        if relationship_source is None or relationship_target is None:
            raise IngestionValidationError("relationship endpoint is not present in nodes")
        raw_properties = getattr(raw_relationship, "properties", {})
        if not isinstance(raw_properties, Mapping):
            raise IngestionValidationError("relationship properties must be a mapping")
        properties = {}
        for key, value in raw_properties.items():
            property_key = str(key)
            if property_key in ALLOWED_RELATIONSHIP_PROPERTIES:
                properties[property_key] = _scalar_property(value)
        relationship_key = (
            str(relationship_source.id),
            relationship_type,
            str(relationship_target.id),
        )
        if relationship_key in seen_relationships:
            continue
        seen_relationships.add(relationship_key)
        normalized_relationships.append(
            Relationship(
                source=relationship_source,
                target=relationship_target,
                type=relationship_type,
                properties=properties,
            )
        )

    return GraphDocument(
        nodes=normalized_nodes,
        relationships=normalized_relationships,
        source=_source_as_document(_graph_source(raw_graph, source, source_by_id)),
    )


def normalize_graph_documents(
    sources: Sequence[SourceDocument],
    raw_graph_documents: Sequence[object],
    *,
    limits: IngestionLimits | None = None,
) -> list[GraphDocument]:
    """Normalize fake or library GraphDocument output to the CIAR allow-list."""
    effective_limits = limits or IngestionLimits()
    source_by_id = {source.document_id: source for source in sources}
    if len(sources) == 1:
        assignments = [sources[0] for _ in raw_graph_documents]
    elif len(raw_graph_documents) == len(sources):
        assignments = list(sources)
    else:
        raise IngestionValidationError("transformer output cannot be mapped to source documents")
    return [
        _normalize_graph_document(raw_graph, assignment, effective_limits, source_by_id)
        for raw_graph, assignment in zip(raw_graph_documents, assignments, strict=True)
    ]


def transform_documents(
    sources: Sequence[SourceDocument],
    *,
    transformer: GraphTransformerLike,
    writer: GraphDocumentWriter | None = None,
    credentials: IngestionCredentials | None = None,
    write: bool = False,
    authorize_write: bool = False,
    limits: IngestionLimits | None = None,
) -> IngestionResult:
    """Transform bounded sources and optionally write only after an explicit gate."""
    effective_limits = limits or IngestionLimits()
    validated_sources = _validate_sources(sources, effective_limits)
    if write and not authorize_write:
        raise IngestionAuthorizationError("writing requires the explicit --write gate")
    if write and writer is None:
        raise IngestionAuthorizationError("writing requires a dedicated ingestion writer")
    if write and credentials is None:
        raise IngestionAuthorizationError("writing requires dedicated ingestion credentials")

    normalized_documents: list[GraphDocument] = []
    for start in range(0, len(validated_sources), effective_limits.batch_size):
        source_batch = validated_sources[start : start + effective_limits.batch_size]
        raw_documents = transformer.convert_to_graph_documents(
            [_source_as_document(source) for source in source_batch]
        )
        normalized_batch = normalize_graph_documents(
            source_batch, raw_documents, limits=effective_limits
        )
        if write:
            cast(GraphDocumentWriter, writer).write(normalized_batch)
        normalized_documents.extend(normalized_batch)
    return IngestionResult(tuple(normalized_documents), len(validated_sources), write)


class Neo4jGraphWriter:
    """Auditable adapter around LangChain Neo4j's fixed GraphDocument writer."""

    def __init__(self, graph: Any, credentials: IngestionCredentials) -> None:
        self._graph = graph
        self.credentials = credentials

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> Neo4jGraphWriter:
        credentials = select_ingestion_credentials(environ)
        if credentials is None:
            raise IngestionAuthorizationError("dedicated NEO4J_INGEST_* credentials are required")
        from langchain_neo4j import Neo4jGraph

        graph = Neo4jGraph(
            url=credentials.uri,
            username=credentials.user,
            password=credentials.password,
            database=credentials.database,
            refresh_schema=False,
            enhanced_schema=False,
        )
        return cls(graph, credentials)

    def write(self, graph_documents: list[GraphDocument]) -> None:
        """Use the library helper; no generated Cypher or delete operation is exposed."""
        self._graph.add_graph_documents(
            graph_documents,
            include_source=False,
            baseEntityLabel=False,
        )

    def close(self) -> None:
        self._graph.close()


def _document_id_for_path(path: Path) -> str:
    digest = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:24]
    return f"file-{digest}"


def _read_bounded_file(path: Path, limits: IngestionLimits) -> str:
    try:
        if not path.is_file() or path.stat().st_size > min(
            MAX_SOURCE_BYTES, limits.max_document_chars * 4
        ):
            raise IngestionValidationError(f"source file is missing or exceeds bounds: {path.name}")
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise IngestionValidationError(f"cannot read source file: {path.name}") from exc


def _json_sources(path: Path, payload: object) -> list[SourceDocument]:
    entries = payload if isinstance(payload, list) else [payload]
    if not entries:
        raise IngestionValidationError("JSON document list cannot be empty")
    sources: list[SourceDocument] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise IngestionValidationError("JSON entries must be objects")
        allowed_keys = {"id", "document_id", "text", "content"}
        if set(entry) - allowed_keys:
            raise IngestionValidationError("JSON contains unsupported document fields")
        document_id = entry.get("document_id", entry.get("id"))
        if document_id is None:
            document_id = f"{_document_id_for_path(path)}-{index}"
        content = entry.get("text", entry.get("content"))
        if content is None:
            raise IngestionValidationError("JSON document requires text or content")
        sources.append(SourceDocument(str(document_id), cast(str, content), path.name))
    return sources


def load_source_documents(
    paths: Sequence[str | Path], *, limits: IngestionLimits | None = None
) -> list[SourceDocument]:
    """Load only local text, Markdown, or explicitly shaped JSON documents."""
    effective_limits = limits or IngestionLimits()
    if len(paths) > effective_limits.max_documents:
        raise IngestionValidationError(
            f"source count exceeds max_documents={effective_limits.max_documents}"
        )
    sources: list[SourceDocument] = []
    for raw_path in paths:
        path = Path(raw_path)
        suffix = path.suffix.casefold()
        if suffix not in {".txt", ".md", ".markdown", ".json"}:
            raise IngestionValidationError(f"unsupported source extension: {path.name}")
        raw_text = _read_bounded_file(path, effective_limits)
        if suffix == ".json":
            try:
                parsed = json.loads(raw_text)
            except json.JSONDecodeError as exc:
                raise IngestionValidationError(f"invalid JSON source: {path.name}") from exc
            sources.extend(_json_sources(path, parsed))
        else:
            sources.append(SourceDocument(_document_id_for_path(path), raw_text, path.name))
    if len(sources) > effective_limits.max_documents:
        raise IngestionValidationError(
            f"source count exceeds max_documents={effective_limits.max_documents}"
        )
    return sources
