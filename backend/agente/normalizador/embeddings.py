"""Scoped, injectable semantic retrieval for curricular context.

Vectors are an implementation detail. The public retrieval interface exposes
only catalog candidates, score, and opaque audit identifiers.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol, cast

from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, ConceptoCHH

SourceKind = Literal["career_curriculum", "labor"]
CHH_OUTPUT_TYPES = ("competencia", "habilidad", "herramienta")
DEFAULT_EMBEDDING_LIMITS = {tipo: 12 for tipo in CHH_OUTPUT_TYPES}
DEFAULT_MINIMUM_SIMILARITY = 0.0

# Safe, stable values persisted in fallback audit records. They deliberately
# contain no provider error details, paths, credentials, or request data.
FALLBACK_REASON_RETRIEVER_ABSENT = "embedding_retriever_absent"
FALLBACK_REASON_CATALOG_EMPTY = "embedding_catalog_empty"
FALLBACK_REASON_PROVIDER_OR_VECTOR_INVALID = "embedding_provider_or_vector_invalid"
FALLBACK_REASON_CANDIDATES_BELOW_THRESHOLD = "embedding_candidates_below_threshold"
_FALLBACK_REASON_CODES = frozenset(
    (
        FALLBACK_REASON_RETRIEVER_ABSENT,
        FALLBACK_REASON_CATALOG_EMPTY,
        FALLBACK_REASON_PROVIDER_OR_VECTOR_INVALID,
        FALLBACK_REASON_CANDIDATES_BELOW_THRESHOLD,
    )
)


class EmbeddingProvider(Protocol):
    """Minimal provider seam implemented by deterministic fakes and adapters."""

    def embed_query(self, text: str) -> Sequence[float]: ...

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class EmbeddingUnavailable(RuntimeError):
    """Semantic retrieval could not provide trustworthy candidates."""

    def __init__(
        self,
        message: str,
        *,
        reason_code: str = FALLBACK_REASON_PROVIDER_OR_VECTOR_INVALID,
    ) -> None:
        super().__init__(message)
        self.reason_code = (
            reason_code
            if reason_code in _FALLBACK_REASON_CODES
            else FALLBACK_REASON_PROVIDER_OR_VECTOR_INVALID
        )


@dataclass(frozen=True, slots=True)
class CatalogDocument:
    """One catalog concept in an explicit curriculum or global labor scope."""

    id: str
    text: str
    source_kind: SourceKind
    career: str | None
    period: str | None
    type: str
    catalog_version: str
    name: str = ""
    description: str = ""

    def __post_init__(self) -> None:
        if self.source_kind not in ("career_curriculum", "labor"):
            raise ValueError("unsupported embedding source scope")
        if self.source_kind == "career_curriculum":
            if not self.career or not self.period:
                raise ValueError("career curriculum documents require career and period")
        elif self.career is not None or self.period is not None:
            raise ValueError("labor documents must use the explicit global scope")

    @property
    def identity(self) -> str:
        """Immutable cache identity; bare concept IDs are not unique enough."""

        scope = (
            f"career:{self.career}:period:{self.period}"
            if self.source_kind == "career_curriculum"
            else "global"
        )
        text_hash = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        return "|".join(
            (self.source_kind, scope, self.catalog_version, self.type, self.id, text_hash)
        )

    def prompt_dict(
        self, *, similarity: float, method: str, model: str | None, config: str | None
    ) -> dict[str, object]:
        return {
            "id": self.id,
            "nombre": self.name or self.text,
            "descripcion": self.description or self.text,
            "tipo": self.type,
            "texto": self.text,
            "source_kind": self.source_kind,
            "career": self.career,
            "period": self.period,
            "type": self.type,
            "catalog_version": self.catalog_version,
            "similarity": round(similarity, 6),
            "retrieval_method": method,
            "model": model,
            "config": config,
        }


@dataclass(frozen=True, slots=True)
class EmbeddingScope:
    """An explicit non-mergeable retrieval scope."""

    career: str | None = None
    period: str | None = None
    source_kinds: tuple[SourceKind, ...] = ("career_curriculum",)

    def __post_init__(self) -> None:
        if self.source_kinds == ("career_curriculum",):
            if not self.career or not self.period:
                raise ValueError("career curriculum scope requires career and period")
            return
        if self.source_kinds == ("labor",):
            if self.career is not None or self.period is not None:
                raise ValueError("labor scope is global and cannot include career or period")
            return
        raise ValueError("embedding scopes cannot merge curriculum and labor sources")

    @classmethod
    def curriculum(cls, career: str, period: str) -> EmbeddingScope:
        return cls(career=career, period=period)

    @classmethod
    def labor_global(cls) -> EmbeddingScope:
        return cls(source_kinds=("labor",))

    def allows(self, document: CatalogDocument) -> bool:
        if self.source_kinds == ("labor",):
            return document.source_kind == "labor"
        return (
            document.source_kind == "career_curriculum"
            and document.career == self.career
            and document.period == self.period
        )

    def a_dict(self) -> dict[str, object]:
        return {
            "scope_kind": (
                "labor_global" if self.source_kinds == ("labor",) else "career_curriculum"
            ),
            "career": self.career,
            "period": self.period,
            "source_kinds": list(self.source_kinds),
        }


@dataclass(frozen=True, slots=True)
class RetrievedCandidate:
    document: CatalogDocument
    similarity: float
    method: str
    model: str | None
    config: str | None

    def a_dict(self) -> dict[str, object]:
        return self.document.prompt_dict(
            similarity=self.similarity, method=self.method, model=self.model, config=self.config
        )


class InMemoryEmbeddingIndex:
    """Provider- and scope-safe in-memory vector cache."""

    def __init__(self, documents: Iterable[CatalogDocument]) -> None:
        self.documents = tuple(documents)
        identities = [document.identity for document in self.documents]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate embedding document identity")
        self._vectors: dict[tuple[str, str], tuple[float, ...]] = {}

    def vectors_for(
        self,
        provider: EmbeddingProvider,
        provider_fingerprint: str,
        documents: Sequence[CatalogDocument],
    ) -> Mapping[str, tuple[float, ...]]:
        missing = [
            document
            for document in documents
            if (provider_fingerprint, document.identity) not in self._vectors
        ]
        if missing:
            try:
                vectors = provider.embed_documents([document.text for document in missing])
                if len(vectors) != len(missing):
                    raise ValueError("embedding count does not match document count")
                normalized = tuple(_normalizar_vector(vector) for vector in vectors)
                self._vectors.update(
                    {
                        (provider_fingerprint, document.identity): vector
                        for document, vector in zip(missing, normalized, strict=True)
                    }
                )
            except EmbeddingUnavailable:
                raise
            except Exception as exc:
                raise EmbeddingUnavailable(f"document embedding failed: {exc}") from exc
        return {
            document.identity: self._vectors[(provider_fingerprint, document.identity)]
            for document in documents
        }


class EmbeddingRetriever:
    """Deep retrieval interface for explicit scope, ranking, limits and audit."""

    def __init__(
        self,
        provider: EmbeddingProvider | None,
        index: InMemoryEmbeddingIndex,
        *,
        config_identifier: str | None = None,
        minimum_similarity: float | None = None,
    ) -> None:
        self.provider = provider
        self.index = index
        self.minimum_similarity = normalizar_similitud_minima(minimum_similarity)
        self._provider_fingerprint = _provider_fingerprint(provider, config_identifier)
        self.config_identifier = f"provider:{self._provider_fingerprint}" if provider else None

    @property
    def model_identifier(self) -> str | None:
        return _model_identifier(self.provider)

    def retrieve(
        self,
        query: str,
        *,
        scope: EmbeddingScope | None = None,
        limits: Mapping[str, int] | None = None,
        pool_size: int | None = None,
    ) -> dict[str, tuple[RetrievedCandidate, ...]]:
        """Retrieve independently for one logro.

        ``pool_size`` is an optional *per-type* ranking pool before each type's
        final limit. ``None`` leaves the pool unbounded; zero returns no
        candidates. It never shares candidate results between logro calls.
        """

        if self.provider is None:
            raise EmbeddingUnavailable(
                "no embedding provider configured",
                reason_code=FALLBACK_REASON_PROVIDER_OR_VECTOR_INVALID,
            )
        if scope is None:
            raise EmbeddingUnavailable(
                "explicit scope is required for embedding retrieval",
                reason_code=FALLBACK_REASON_PROVIDER_OR_VECTOR_INVALID,
            )
        active_limits = normalizar_limites(limits, defaults=DEFAULT_EMBEDDING_LIMITS)
        pool = _validar_pool(pool_size)
        eligible = tuple(document for document in self.index.documents if scope.allows(document))
        if not eligible:
            raise EmbeddingUnavailable(
                "empty embedding catalog for requested scope",
                reason_code=FALLBACK_REASON_CATALOG_EMPTY,
            )
        try:
            query_vector = _normalizar_vector(self.provider.embed_query(query))
            vectors = self.index.vectors_for(self.provider, self._provider_fingerprint, eligible)
            scored = [
                (document, _cosine_similarity(query_vector, vectors[document.identity]))
                for document in eligible
            ]
        except EmbeddingUnavailable:
            raise
        except Exception as exc:
            raise EmbeddingUnavailable(
                f"query embedding failed: {exc}",
                reason_code=FALLBACK_REASON_PROVIDER_OR_VECTOR_INVALID,
            ) from exc

        resultado: dict[str, tuple[RetrievedCandidate, ...]] = {}
        for tipo, limite in active_limits.items():
            candidatos = sorted(
                (
                    item
                    for item in scored
                    if item[0].type == tipo and item[1] > self.minimum_similarity
                ),
                key=lambda item: (-item[1], item[0].id, item[0].identity),
            )
            if pool is not None:
                candidatos = candidatos[:pool]
            resultado[tipo] = tuple(
                RetrievedCandidate(
                    document=document,
                    similarity=score,
                    method="embedding",
                    model=self.model_identifier,
                    config=self.config_identifier,
                )
                for document, score in candidatos[:limite]
            )
        if any(active_limits.values()) and not any(resultado.values()):
            raise EmbeddingUnavailable(
                "no embedding candidates exceeded the minimum similarity",
                reason_code=FALLBACK_REASON_CANDIDATES_BELOW_THRESHOLD,
            )
        return resultado


class OpenAIEmbeddingProvider:
    """Lazy adapter: importing or constructing it never initializes a client."""

    def __init__(self, model_name: str | None = None) -> None:
        self.model_name: str = model_name or os.getenv("NORMALIZADOR_EMBEDDING_MODEL") or (
            "text-embedding-3-small"
        )
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            from langchain_openai import OpenAIEmbeddings

            self._client = OpenAIEmbeddings(model=self.model_name)
        return self._client

    def embed_query(self, text: str) -> Sequence[float]:
        return cast(Sequence[float], self._get_client().embed_query(text))

    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        return cast(Sequence[Sequence[float]], self._get_client().embed_documents(list(texts)))


def crear_retriever_curricular_opt_in(
    catalogo: CatalogoCHH,
    *,
    career: str,
    period: str,
    enabled: bool,
    provider: EmbeddingProvider | None = None,
) -> EmbeddingRetriever | None:
    """Build the production retriever only after the explicit runtime opt-in."""

    if not enabled or not career or not period:
        return None
    if provider is None:
        if not os.getenv("OPENAI_API_KEY"):
            return None
        provider = OpenAIEmbeddingProvider()
    try:
        return EmbeddingRetriever(
            provider,
            InMemoryEmbeddingIndex(
                documentos_desde_catalogo(catalogo, career=career, period=period)
            ),
        )
    except (TypeError, ValueError):
        return None


def documentos_desde_catalogo(
    catalogo: CatalogoCHH,
    *,
    career: str,
    period: str,
    source_kind: SourceKind = "career_curriculum",
) -> tuple[CatalogDocument, ...]:
    """Project a catalog into one explicit curriculum scope."""

    if source_kind != "career_curriculum":
        raise ValueError("labor documents must be provided with their global source scope")
    documentos: list[CatalogDocument] = []
    for tipo, conceptos in (
        ("competencia", catalogo.competencias),
        ("habilidad", catalogo.habilidades),
        ("herramienta", catalogo.herramientas),
    ):
        documentos.extend(
            _documento_concepto(concepto, tipo, catalogo.version, career, period)
            for concepto in conceptos
        )
    return tuple(documentos)


def normalizar_similitud_minima(value: float | None = None) -> float:
    """Return a safe semantic threshold; zero and negative scores never pass."""

    configured = (
        os.getenv(
            "NORMALIZADOR_CURRICULAR_EMBEDDING_MIN_SIMILARITY",
            str(DEFAULT_MINIMUM_SIMILARITY),
        )
        if value is None
        else value
    )
    if isinstance(configured, bool):
        raise ValueError("minimum embedding similarity must be a number")
    try:
        similarity = float(configured)
    except (TypeError, ValueError) as exc:
        raise ValueError("minimum embedding similarity must be a number") from exc
    if not math.isfinite(similarity) or not 0.0 <= similarity < 1.0:
        raise ValueError("minimum embedding similarity must be in [0, 1)")
    return similarity


def normalizar_limites(
    limits: Mapping[str, int] | None,
    *,
    defaults: Mapping[str, int],
) -> dict[str, int]:
    """Validate limits once; ``None`` uses defaults and ``{}`` requests none."""

    if limits is None:
        source: Mapping[str, int] = defaults
    elif not isinstance(limits, Mapping):
        raise ValueError("embedding limits must be a mapping")
    else:
        desconocidos = set(limits) - set(CHH_OUTPUT_TYPES)
        if desconocidos:
            raise ValueError(f"unknown embedding limit types: {sorted(desconocidos)}")
        source = limits
    resultado: dict[str, int] = {}
    for tipo in CHH_OUTPUT_TYPES:
        valor = source.get(tipo, 0)
        if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
            raise ValueError("embedding limits must be non-negative integers")
        resultado[tipo] = valor
    return resultado


def _documento_concepto(
    concepto: ConceptoCHH, tipo: str, version: str, career: str, period: str
) -> CatalogDocument:
    return CatalogDocument(
        id=concepto.id,
        text=f"{concepto.nombre}. {concepto.descripcion}".strip(),
        source_kind="career_curriculum",
        career=career,
        period=period,
        type=tipo,
        catalog_version=version,
        name=concepto.nombre,
        description=concepto.descripcion,
    )


def _validar_pool(pool_size: int | None) -> int | None:
    if pool_size is None:
        return None
    if isinstance(pool_size, bool) or not isinstance(pool_size, int) or pool_size < 0:
        raise ValueError("pool_size must be a non-negative integer")
    return pool_size


def _normalizar_vector(vector: Sequence[float]) -> tuple[float, ...]:
    resultado = tuple(float(valor) for valor in vector)
    if not resultado or not all(math.isfinite(valor) for valor in resultado):
        raise ValueError("invalid embedding vector")
    if math.sqrt(sum(valor * valor for valor in resultado)) == 0:
        raise ValueError("embedding vector has zero norm")
    return resultado


def _cosine_similarity(primero: Sequence[float], segundo: Sequence[float]) -> float:
    if len(primero) != len(segundo):
        raise ValueError("embedding dimensions do not match")
    return sum(a * b for a, b in zip(primero, segundo, strict=True)) / (
        math.sqrt(sum(valor * valor for valor in primero))
        * math.sqrt(sum(valor * valor for valor in segundo))
    )


def _model_identifier(provider: EmbeddingProvider | None) -> str | None:
    if provider is None:
        return None
    return next(
        (
            str(getattr(provider, atributo))
            for atributo in ("model_name", "model")
            if getattr(provider, atributo, None)
        ),
        provider.__class__.__name__,
    )


def _provider_fingerprint(provider: EmbeddingProvider | None, explicit_config: str | None) -> str:
    if provider is None:
        return "unconfigured"
    config = explicit_config or getattr(provider, "config_identifier", "")
    payload = json.dumps(
        {
            "provider": f"{provider.__class__.__module__}.{provider.__class__.__qualname__}",
            "model": _model_identifier(provider),
            "config": str(config),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
