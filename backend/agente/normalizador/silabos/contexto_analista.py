"""Contexto auditable y payload semántico para el analista curricular."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping
from typing import Any, cast

from agente.normalizador.embeddings import (
    FALLBACK_REASON_CANDIDATES_BELOW_THRESHOLD,
    FALLBACK_REASON_CATALOG_EMPTY,
    FALLBACK_REASON_PROVIDER_OR_VECTOR_INVALID,
    FALLBACK_REASON_RETRIEVER_ABSENT,
    EmbeddingRetriever,
    EmbeddingScope,
)
from agente.normalizador.empleabilidad.catalogo import CatalogoCHH, clave_concepto
from agente.normalizador.identidad import hashed
from agente.normalizador.silabos.contexto_curricular import (
    _sanear_perfil_transportable,
    construir_contexto_por_logro,
)
from agente.normalizador.silabos.entrada import PATRON_PERIODO
from agente.normalizador.silabos.herramientas import es_herramienta_concreta

_METODOS_RECUPERACION_AUDITABLES = frozenset(("embedding", "lexical"))
_REASON_CODES_RECUPERACION_AUDITABLES = frozenset(
    (
        FALLBACK_REASON_RETRIEVER_ABSENT,
        FALLBACK_REASON_CATALOG_EMPTY,
        FALLBACK_REASON_PROVIDER_OR_VECTOR_INVALID,
        FALLBACK_REASON_CANDIDATES_BELOW_THRESHOLD,
    )
)
_IDENTIFICADOR_AUDITABLE = re.compile(r"[A-Za-z0-9_.:-]{1,120}")
_ETIQUETA_SCOPE_AUDITABLE = re.compile(r"[A-Z0-9_-]{1,80}")
_PERIODO_SCOPE_AUDITABLE = PATRON_PERIODO
_FINGERPRINT_AUDITABLE = re.compile(r"[0-9a-f]{16}")
_MARCADORES_SECRETOS = ("api", "key", "token", "secret", "password", "sk-")
_RECURSOS_ENSENANZA_GENERICOS = {
    "aula virtual",
    "diapositivas",
    "lecturas",
    "material didactico",
    "recursos de aprendizaje",
    "recursos educativos",
    "video tutorial",
    "videos tutoriales",
}


def _prompt_analista(
    lote: tuple[dict[str, object], ...],
    perfil_prompt: dict[str, object],
    carrera: str,
    periodo: str,
) -> str:
    return (
        "Eres el analista curricular senior de una universidad. Trabajas con el perfil "
        f"de {carrera} del periodo {periodo}. El sílabo es la única fuente de verdad.\n\n"
        "Tu tarea es representar TODOS los logros específicos, no reducirlos a los matches "
        "del catálogo. Propón una habilidad observable por logro, una competencia profesional "
        "que agrupe la habilidad y TODAS las herramientas que el sílabo cite literalmente. "
        "Toda herramienta concreta nombrada en el sílabo debe proponerse con su cita exacta: "
        "lenguajes (Python, Java, JavaScript, SQL), librerías y frameworks (React, Flutter, "
        "Node.js), IDE y editores (VS Code, IntelliJ), sistemas operativos (Linux, Windows), "
        "servicios y plataformas (Meta Ads, Google Ads, GitHub, Docker, Unity) y sistemas "
        "empresariales (SAP, ERP). Evita frases genéricas como 'herramientas de X', "
        "'software de análisis' o 'plataformas digitales': nombra el producto concreto. "
        "Puedes crear conceptos nuevos si el sílabo los respalda. No inventes identificadores ni "
        "evidencia. "
        "Ningún logro puede quedar sin habilidad ni competencia: aunque el sílabo no cite "
        "herramientas, la habilidad y la competencia se proponen igual con la evidencia del logro. "
        "La competencia debe ser un dominio profesional específico (por ejemplo: Desarrollo de "
        "aplicaciones web, Administración de sistemas ERP, Seguridad ofensiva, Modelado de datos, "
        "Desarrollo de videojuegos). Nunca propongas competencias transversales o institucionales "
        "(Trabajo colaborativo, Pensamiento crítico, Comunicación efectiva, Experimentación, "
        "Solución creativa de problemas, Curiosidad por el conocimiento, Aprendizaje autónomo): "
        "si el sílabo solo declara esas, deriva la competencia de dominio desde la evidencia "
        "técnica semanal. "
        "No uses "
        "taxonomías de otra carrera: usa el perfil entregado como contexto específico.\n\n"
        "Perfil curado y defensivo:\n"
        f"{json.dumps(_perfil_semantico(perfil_prompt), ensure_ascii=False, indent=2)}\n\n"
        "Devuelve una decisión por cada logro, en el mismo orden en que aparecen los logros "
        "del contexto, incluso si requiere_revision=true. No devuelvas identificadores ni códigos "
        "de control. Incluye el texto literal del logro en el campo logro para que Python valide "
        "la correspondencia; ese texto no es un identificador. "
        "La habilidad debe comenzar con una acción profesional y tener verbo + objeto. La "
        "evidencia debe copiar fragmentos exactos del caso.\n\n"
        f"CASOS:\n{json.dumps(_payload_semantico_lote(lote), ensure_ascii=False, indent=2)}"
    )


def version_prompt_analista() -> str:
    """Huella estable de la plantilla del prompt para invalidar cachés al editarla."""

    return hashlib.sha256(_prompt_analista((), {}, "", "").encode("utf-8")).hexdigest()[:16]


def _perfil_semantico(perfil_prompt: Mapping[str, object]) -> dict[str, object]:
    """El perfil aporta reglas de negocio, no revisiones ni huellas internas."""

    return cast(dict[str, object], _sanear_perfil_transportable(perfil_prompt))


def _propuesta_semantica(decision: Any) -> dict[str, object]:
    """Proyecta una propuesta inspeccionable sin exponer linaje interno."""

    return {
        "competencia": decision.competencia.model_dump(mode="json"),
        "habilidad": decision.habilidad.model_dump(mode="json"),
        "herramientas": [item.model_dump(mode="json") for item in decision.herramientas],
        "evidencia": decision.evidencia,
        "justificacion": decision.justificacion,
        "confianza": decision.confianza,
        "requiere_revision": decision.requiere_revision,
    }


def _payload_semantico_lote(lote: tuple[dict[str, object], ...]) -> list[dict[str, object]]:
    """Agrupa el contexto de cada sílabo y deja los IDs exclusivamente en Python."""

    contextos: dict[str, dict[str, object]] = {}
    for indice, caso in enumerate(lote):
        clave = str(caso.get("id_silabo") or f"orden-{indice}")
        contexto = contextos.get(clave)
        if contexto is None:
            contexto = {
                "curso": str(caso.get("curso") or ""),
                "sumilla": str(caso.get("sumilla") or ""),
                "logro_general": str(caso.get("logro_general") or ""),
                "competencias_declaradas": _competencias_semanticas(
                    caso.get("competencias_declaradas")
                ),
                "temas_programa": _temas_programa_semanticos(caso),
                "logros_especificos": [],
            }
            contextos[clave] = contexto
        logro = str(caso.get("logro") or "").strip()
        if logro:
            cast(list[str], contexto["logros_especificos"]).append(logro)
    return list(contextos.values())


def _competencias_semanticas(valor: object) -> list[dict[str, str]]:
    if not isinstance(valor, list):
        return []
    resultado: list[dict[str, str]] = []
    for item in valor:
        if not isinstance(item, Mapping):
            continue
        nombre = str(item.get("nombre") or "").strip()
        descripcion = str(item.get("descripcion") or "").strip()
        if nombre or descripcion:
            resultado.append({"nombre": nombre, "descripcion": descripcion})
    return resultado


def _temas_programa_semanticos(caso: Mapping[str, object]) -> list[str]:
    detalle = caso.get("programa_analitico_detalle")
    filas = detalle if isinstance(detalle, list) and detalle else caso.get("programa_analitico")
    if not isinstance(filas, list):
        return []
    temas: list[str] = []
    for fila in filas:
        if isinstance(fila, Mapping):
            tema = re.sub(r"\s+", " ", str(fila.get("tema") or "")).strip()
            contenido = re.sub(r"\s+", " ", str(fila.get("contenido") or "")).strip()
            texto = " | ".join(parte for parte in (tema, contenido) if parte)
            if not texto:
                texto = str(fila.get("texto") or "")
        else:
            texto = str(fila or "")
        texto = re.sub(r"^\s*Semana\s+\d+\s*\|\s*", "", texto, flags=re.IGNORECASE)
        if isinstance(fila, Mapping) and not (fila.get("tema") or fila.get("contenido")):
            texto = re.sub(r"\s+\d+(?:[.,]\d+)?\s*$", "", texto).strip()
        if texto:
            temas.append(texto)
    return temas


def _casos_curriculares(
    registros: list[dict[str, object]],
    catalogo: CatalogoCHH,
    perfil: dict[str, object],
    *,
    retriever: EmbeddingRetriever | None = None,
    embedding_scope: EmbeddingScope | None = None,
    limites_candidatos: Mapping[str, int] | None = None,
    limites_lexicales: Mapping[str, int] | None = None,
    pool_retrieval: int | None = None,
    limite_ejemplos: int = 3,
    crear_id_habilidad: Callable[[str, str, str, str], str] | None = None,
) -> Iterable[dict[str, object]]:
    crear_id_habilidad = crear_id_habilidad or hashed
    for registro in registros:
        datos = registro.get("datos")
        if not isinstance(datos, dict):
            continue
        id_silabo = str(registro.get("id_silabo") or "")
        declaraciones = datos.get("competencias_declaradas")
        outcomes = datos.get("logros_especificos")
        if not isinstance(outcomes, list):
            continue
        contexto = " ".join(
            str(datos.get(campo) or "")
            for campo in ("curso", "sumilla", "logro_general", "texto_relevante")
        )
        for indice_logro, logro in enumerate(outcomes, start=1):
            if not isinstance(logro, dict):
                continue
            descripcion = str(logro.get("descripcion") or "").strip()
            if not descripcion:
                continue
            orden_logro = str(logro.get("orden") or indice_logro)
            evidencia_herramientas = datos.get("herramientas_evidencia")
            evidencias_estructuradas = (
                list(evidencia_herramientas) if isinstance(evidencia_herramientas, list) else []
            )
            evidencias_estructuradas.extend(_evidencias_programa_analitico(datos))
            evidencias_estructuradas = _deduplicar_evidencias_herramientas(evidencias_estructuradas)
            herramientas: list[str] = []
            for item in evidencias_estructuradas:
                if isinstance(item, dict):
                    herramientas.extend(
                        concepto.nombre
                        for concepto in catalogo.buscar(str(item.get("texto") or "")).get(
                            "herramienta", ()
                        )
                        if es_herramienta_concreta(concepto.nombre)
                    )
            caso: dict[str, object] = {
                "id_habilidad_fuente": crear_id_habilidad(
                    "HAB_SRC", id_silabo, orden_logro, descripcion
                ),
                "id_silabo": id_silabo,
                "curso": str(datos.get("curso") or ""),
                "sumilla": str(datos.get("sumilla") or ""),
                "logro_general": str(datos.get("logro_general") or ""),
                "logro": descripcion,
                "competencias_declaradas": declaraciones if isinstance(declaraciones, list) else [],
                "programa_analitico": datos.get("programa_analitico")
                if isinstance(datos.get("programa_analitico"), list)
                else [],
                "programa_analitico_detalle": datos.get("programa_analitico_detalle")
                if isinstance(datos.get("programa_analitico_detalle"), list)
                else [],
                "contenido_relacionado": contexto[:5000],
                "herramientas_detectadas": sorted(set(herramientas)),
                "evidencia_herramientas": evidencias_estructuradas,
                "evidencia_herramientas_candidata": [
                    *evidencias_estructuradas,
                    {"seccion": "Logro de aprendizaje", "texto": descripcion},
                ],
            }
            caso["contexto_recuperado"] = construir_contexto_por_logro(
                caso,
                catalogo,
                perfil,
                retriever=retriever,
                embedding_scope=embedding_scope,
                limites_candidatos=limites_candidatos,
                limites_lexicales=limites_lexicales,
                pool_retrieval=pool_retrieval,
                limite_ejemplos=limite_ejemplos,
            )
            yield caso


def _auditoria_contexto(
    casos: tuple[dict[str, object], ...], contexto_perfil: dict[str, object]
) -> dict[str, object]:
    """Persist only the retrieval metadata needed to audit each logro safely."""

    perfil = cast(dict[str, str], contexto_perfil["perfil_referencia"])
    recuperacion = tuple(
        item for caso in casos if (item := _recuperacion_auditable_por_logro(caso)) is not None
    )
    payload = json.dumps(
        [item["fingerprint"] for item in recuperacion], ensure_ascii=False, separators=(",", ":")
    )
    return {
        "version_contexto": contexto_perfil["version_contexto"],
        "version_catalogo": cast(dict[str, object], contexto_perfil["catalogo"])["version"],
        "estado_perfil": perfil["estado"],
        "revision_perfil": perfil["revision"],
        "hash_perfil": perfil["hash"],
        "hash_contextos": hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16],
        "recuperacion_por_logro": list(recuperacion),
    }


def _recuperacion_auditable_por_logro(caso: dict[str, object]) -> dict[str, object] | None:
    """Project a per-logro context into a deliberately narrow audit record."""

    contexto = caso.get("contexto_recuperado")
    if not isinstance(contexto, dict) or not isinstance(
        recuperacion := contexto.get("recuperacion"), dict
    ):
        return None
    id_habilidad = _texto_auditable(caso.get("id_habilidad_fuente"))
    fingerprint = _fingerprint_auditable(contexto.get("fingerprint"))
    if id_habilidad is None or fingerprint is None:
        return None
    method = recuperacion.get("method")
    reason_code = recuperacion.get("reason_code")
    return {
        "id_habilidad_fuente": id_habilidad,
        "fingerprint": fingerprint,
        "method": method if method in _METODOS_RECUPERACION_AUDITABLES else None,
        "reason_code": (
            reason_code if reason_code in _REASON_CODES_RECUPERACION_AUDITABLES else None
        ),
        "scope": _scope_recuperacion_auditable(recuperacion.get("scope")),
        "model": _modelo_auditable(recuperacion.get("model")),
        "config": _configuracion_auditable(recuperacion.get("config")),
        "minimum_similarity": _minimum_similarity_auditable(recuperacion.get("minimum_similarity")),
    }


def _texto_auditable(valor: object) -> str | None:
    texto = str(valor or "")
    return texto if _IDENTIFICADOR_AUDITABLE.fullmatch(texto) else None


def _modelo_auditable(valor: object) -> str | None:
    texto = _texto_auditable(valor)
    if texto is None or any(marcador in texto.casefold() for marcador in _MARCADORES_SECRETOS):
        return None
    return texto


def _fingerprint_auditable(valor: object) -> str | None:
    texto = str(valor or "")
    return texto if _FINGERPRINT_AUDITABLE.fullmatch(texto) else None


def _configuracion_auditable(valor: object) -> str | None:
    texto = str(valor or "")
    if not texto.startswith("provider:"):
        return None
    return texto if _FINGERPRINT_AUDITABLE.fullmatch(texto.removeprefix("provider:")) else None


def _etiqueta_scope_auditable(valor: object) -> str | None:
    texto = str(valor or "")
    return texto if _ETIQUETA_SCOPE_AUDITABLE.fullmatch(texto) else None


def _periodo_scope_auditable(valor: object) -> str | None:
    texto = str(valor or "")
    return texto if _PERIODO_SCOPE_AUDITABLE.fullmatch(texto) else None


def _minimum_similarity_auditable(valor: object) -> float | None:
    """Keep only the safe threshold actually applied by the retriever."""

    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    minimo = float(valor)
    return minimo if 0.0 <= minimo < 1.0 else None


def _scope_recuperacion_auditable(valor: object) -> dict[str, object] | None:
    if not isinstance(valor, dict):
        return None
    scope_kind = valor.get("scope_kind")
    source_kinds = valor.get("source_kinds")
    career = _etiqueta_scope_auditable(valor.get("career"))
    period = _periodo_scope_auditable(valor.get("period"))
    if (
        scope_kind == "career_curriculum"
        and source_kinds == ["career_curriculum"]
        and career is not None
        and period is not None
    ):
        return {
            "scope_kind": scope_kind,
            "career": career,
            "period": period,
            "source_kinds": source_kinds,
        }
    if scope_kind == "labor_global" and source_kinds == ["labor"]:
        return {
            "scope_kind": scope_kind,
            "career": None,
            "period": None,
            "source_kinds": source_kinds,
        }
    return None


def _evidencias_programa_analitico(datos: dict[str, object]) -> list[dict[str, str]]:
    """Expone solo contenido curricular útil como evidencia estructurada de herramientas."""

    detalle = datos.get("programa_analitico_detalle")
    if isinstance(detalle, list):
        evidencias_detalle: list[dict[str, str]] = []
        for fila in detalle:
            if not isinstance(fila, dict):
                continue
            texto = str(fila.get("texto") or "").strip()
            clave = clave_concepto(texto)
            if not texto or _programa_es_recurso_no_evidenciable(texto, clave):
                continue
            evidencias_detalle.append(
                {
                    "origen": "programa_analitico",
                    "seccion": "programa_analitico",
                    "texto": texto,
                }
            )
        if evidencias_detalle:
            return evidencias_detalle
    programa = datos.get("programa_analitico")
    if not isinstance(programa, list):
        return []
    evidencias: list[dict[str, str]] = []
    for item in programa:
        texto = str(item).strip()
        clave = clave_concepto(texto)
        if texto and not _programa_es_recurso_no_evidenciable(texto, clave):
            evidencias.append(
                {"origen": "programa_analitico", "seccion": "programa_analitico", "texto": texto}
            )
    return evidencias


def _deduplicar_evidencias_herramientas(evidencias: list[object]) -> list[dict[str, str]]:
    """Preserva la primera evidencia trazable de cada fila curricular."""

    resultado: list[dict[str, str]] = []
    vistos: set[str] = set()
    for item in evidencias:
        if not isinstance(item, dict):
            continue
        seccion = str(item.get("seccion") or "").strip()
        origen = str(item.get("origen") or "").strip()
        texto = str(item.get("texto") or "").strip()
        clave = clave_concepto(texto)
        if seccion and texto and clave and clave not in vistos:
            vistos.add(clave)
            evidencia = {"seccion": seccion, "texto": texto}
            if origen:
                evidencia["origen"] = origen
            resultado.append(evidencia)
    return resultado


def _programa_es_recurso_no_evidenciable(texto: str, clave: str) -> bool:
    texto_minusculas = texto.lower()
    return (
        "bibliografia" in clave
        or "referencia bibliografica" in clave
        or "http://" in texto_minusculas
        or "https://" in texto_minusculas
        or "www." in texto_minusculas
        or any(recurso in clave for recurso in _RECURSOS_ENSENANZA_GENERICOS)
    )
