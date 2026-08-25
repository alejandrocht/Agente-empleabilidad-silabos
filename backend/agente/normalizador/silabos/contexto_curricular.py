"""Contexto curricular recuperado y auditable para cada logro."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import cast

from agente.normalizador.embeddings import (
    DEFAULT_EMBEDDING_LIMITS,
    FALLBACK_REASON_PROVIDER_OR_VECTOR_INVALID,
    FALLBACK_REASON_RETRIEVER_ABSENT,
    EmbeddingRetriever,
    EmbeddingScope,
    EmbeddingUnavailable,
    normalizar_limites,
)
from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, ConceptoCHH

CHH_OUTPUT_TYPES = ("competencia", "habilidad", "herramienta")

_VERSION_CONTEXTO = "contexto-curricular/v2"
_LIMITES_CANDIDATOS = {
    "competencia": 4,
    "habilidad": 6,
    "herramienta": 4,
}
_LIMITE_EJEMPLOS = 3


def construir_contexto_por_logro(
    caso: dict[str, object],
    catalogo: CatalogoCHH,
    perfil: dict[str, object],
    *,
    retriever: EmbeddingRetriever | None = None,
    embedding_scope: EmbeddingScope | None = None,
    limites_candidatos: Mapping[str, int] | None = None,
    pool_retrieval: int | None = None,
) -> dict[str, object]:
    """Construye el único contexto recuperado que ve el LLM para un logro.

    Los candidatos del catálogo son sugerencias trazables, no una restricción
    para el sílabo. La curación sin aprobación humana se limita a reglas
    defensivas: nunca incorpora aliases ni ejemplos positivos.
    """

    consulta = _consulta(caso)
    limites_lexicales = _limites_candidatos(limites_candidatos)
    limites_embedding = normalizar_limites(
        limites_candidatos,
        defaults=DEFAULT_EMBEDDING_LIMITS,
    )
    scope = embedding_scope or _scope_por_defecto(perfil)
    perfil_estado = str(perfil.get("estado") or "BORRADOR").upper()
    perfil_revision = str(perfil.get("revision") or perfil.get("periodo") or "sin_revision")
    retrieval_info = _auditoria_recuperacion(
        "lexical",
        scope,
        None,
        None,
        FALLBACK_REASON_RETRIEVER_ABSENT,
        perfil_estado=perfil_estado,
        perfil_revision=perfil_revision,
    )
    candidatos: dict[str, list[dict[str, object]]]
    if retriever is not None:
        try:
            recuperados_embedding = retriever.retrieve(
                consulta,
                scope=scope,
                limits=limites_embedding,
                pool_size=pool_retrieval,
            )
            candidatos = {
                tipo: [item.a_dict() for item in recuperados_embedding.get(tipo, ())]
                for tipo in CHH_OUTPUT_TYPES
            }
            retrieval_info = _auditoria_recuperacion(
                "embedding",
                scope,
                retriever.model_identifier,
                retriever.config_identifier,
                minimum_similarity=retriever.minimum_similarity,
                perfil_estado=perfil_estado,
                perfil_revision=perfil_revision,
            )
        except EmbeddingUnavailable as exc:
            retrieval_info = _auditoria_recuperacion(
                "lexical",
                scope,
                retriever.model_identifier,
                retriever.config_identifier,
                (
                    exc.reason_code
                    if isinstance(exc.reason_code, str)
                    else FALLBACK_REASON_PROVIDER_OR_VECTOR_INVALID
                ),
                minimum_similarity=retriever.minimum_similarity,
                perfil_estado=perfil_estado,
                perfil_revision=perfil_revision,
            )
            candidatos = _candidatos_lexical(consulta, catalogo, limites_lexicales)
    else:
        candidatos = _candidatos_lexical(consulta, catalogo, limites_lexicales)
    contexto: dict[str, object] = {
        "version_contexto": _VERSION_CONTEXTO,
        "catalogo": {"version": catalogo.version},
        "perfil_referencia": _perfil_referencia(perfil),
        "taxonomia": {"tipos_salida": list(CHH_OUTPUT_TYPES)},
        "regla": (
            "Las únicas salidas curriculares son Competencia, Habilidad y Herramienta. "
            "Los candidatos son sugerencias recuperadas, no decisiones aprobadas. "
            "Puedes proponer un concepto nuevo solo con evidencia explícita del sílabo."
        ),
        "candidatos": candidatos,
        "recuperacion": retrieval_info,
        "ejemplos": [
            ejemplo.a_dict() for ejemplo in catalogo.ejemplos(consulta, limite=_LIMITE_EJEMPLOS)
        ],
        "proveniencia": _proveniencia(caso, perfil, catalogo),
    }
    contexto["fingerprint"] = _fingerprint(contexto)
    return contexto


def _limites_candidatos(limites: Mapping[str, int] | None) -> dict[str, int]:
    return normalizar_limites(limites, defaults=_LIMITES_CANDIDATOS)


def _candidatos_lexical(
    consulta: str,
    catalogo: CatalogoCHH,
    limites: Mapping[str, int],
) -> dict[str, list[dict[str, object]]]:
    recuperados = catalogo.buscar(consulta, limite=max(limites.values(), default=0))
    return {
        tipo: [_candidato_dict(concepto, tipo) for concepto in recuperados.get(tipo, ())[:limite]]
        for tipo, limite in limites.items()
    }


def _scope_por_defecto(perfil: dict[str, object]) -> EmbeddingScope | None:
    carrera = str(perfil.get("carrera") or "").strip() or None
    periodo = str(perfil.get("periodo") or "").strip() or None
    return EmbeddingScope.curriculum(carrera, periodo) if carrera and periodo else None


def _auditoria_recuperacion(
    metodo: str,
    scope: EmbeddingScope | None,
    modelo: str | None,
    configuracion: str | None,
    reason_code: str | None = None,
    minimum_similarity: float | None = None,
    perfil_estado: str | None = None,
    perfil_revision: str | None = None,
) -> dict[str, object]:
    return {
        "method": metodo,
        "scope": scope.a_dict() if scope else None,
        "model": modelo,
        "config": configuracion,
        "reason_code": reason_code,
        "minimum_similarity": minimum_similarity,
        "profile_status": perfil_estado,
        "profile_revision": perfil_revision,
    }


def _consulta(caso: dict[str, object]) -> str:
    return " ".join(
        str(caso.get(campo) or "")
        for campo in (
            "logro",
            "curso",
            "sumilla",
            "logro_general",
            "contenido_relacionado",
        )
    )


def _candidato_dict(concepto: ConceptoCHH, tipo: str) -> dict[str, object]:
    """Añade el tipo CHH de la colección, aunque el CSV no lo declare."""

    resultado: dict[str, object] = dict(concepto.a_dict())
    resultado["tipo"] = tipo
    return resultado


def _proveniencia(
    caso: dict[str, object],
    perfil: dict[str, object],
    catalogo: CatalogoCHH,
) -> dict[str, object]:
    """Expone procedencia compacta sin enviar rutas locales al LLM."""

    campos_fuente = (
        "curso",
        "sumilla",
        "logro_general",
        "logro",
        "contenido_relacionado",
        "evidencia_herramientas",
    )
    secciones = [campo for campo in campos_fuente if caso.get(campo)]
    resultado: dict[str, object] = {
        "universidad": str(perfil.get("universidad") or "Universidad de Lima"),
        "carrera": str(perfil.get("carrera") or ""),
        "periodo": str(perfil.get("periodo") or ""),
        "id_silabo": _texto_corto(caso.get("id_silabo")),
        "id_curso": _texto_corto(caso.get("id_curso")),
        "secciones_fuente": secciones,
        "catalogo_version": catalogo.version,
    }
    return {clave: valor for clave, valor in resultado.items() if valor not in ("", [])}


def _texto_corto(valor: object, limite: int = 120) -> str:
    """Evita que identificadores o metadatos de origen arrastren rutas locales."""

    texto = str(valor or "").replace("\\", "/").split("/")[-1]
    return texto[:limite]


def construir_perfil_para_prompt(perfil: dict[str, object]) -> dict[str, object]:
    """Reduce el perfil a la política que viaja una vez por prompt."""

    return _perfil_contextual(perfil)


def _perfil_referencia(perfil: dict[str, object]) -> dict[str, str]:
    perfil_contextual = _perfil_contextual(perfil)
    return {clave: str(perfil_contextual[clave]) for clave in ("estado", "revision", "hash")}


def _perfil_contextual(perfil: dict[str, object]) -> dict[str, object]:
    estado = str(perfil.get("estado") or "BORRADOR").upper()
    if estado not in {
        "APROBADO",
        "BORRADOR",
        "BORRADOR_CON_PENDIENTES",
        "REQUIERE_REVISION_HUMANA",
    }:
        estado = "BORRADOR"
    resultado: dict[str, object] = {
        "carrera": str(perfil.get("carrera") or ""),
        "periodo": str(perfil.get("periodo") or ""),
        "estado": estado,
        "revision": str(perfil.get("revision") or perfil.get("periodo") or "sin_revision"),
        "hash": _fingerprint(perfil),
        "dominios": _lista(perfil.get("dominios")),
        "reglas": _lista(perfil.get("reglas")),
        "exclusiones": _lista(perfil.get("exclusiones")),
        "contraejemplos": _lista(perfil.get("contraejemplos")),
        "habilidades_evitar": _lista(perfil.get("habilidades_evitar")),
    }
    if estado == "APROBADO":
        resultado["competencias_preferidas"] = _lista(perfil.get("competencias_preferidas"))
        resultado["aliases"] = _coleccion(perfil.get("aliases"))
        resultado["ejemplos_positivos"] = _coleccion(perfil.get("ejemplos"))
    return resultado


def _lista(valor: object) -> list[object]:
    return list(valor) if isinstance(valor, list) else []


def _coleccion(valor: object) -> dict[str, object] | list[object]:
    if isinstance(valor, dict):
        return cast(dict[str, object], valor)
    return _lista(valor)


def _fingerprint(valor: object) -> str:
    payload = json.dumps(valor, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
