"""Clasificación determinista de propuestas curriculares para revisión.

Las coincidencias exactas se deduplican automáticamente sin borrar sus filas
fuente: cada grupo conserva un único representante determinista y las demás
filas quedan como evidencia auditable. Las señales semánticas y las
herramientas sospechosas siguen requiriendo una decisión humana.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from difflib import SequenceMatcher

FLAG_EXACT_DUPLICATE = "EXACT_DUPLICATE"
FLAG_POSSIBLE_SEMANTIC_DUPLICATE = "POSSIBLE_SEMANTIC_DUPLICATE"
FLAG_SUSPICIOUS_UNRELATED_TOOL = "SUSPICIOUS_UNRELATED_TOOL"

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

_STOPWORDS = {
    "a",
    "al",
    "con",
    "de",
    "del",
    "el",
    "en",
    "la",
    "las",
    "lo",
    "los",
    "para",
    "por",
    "un",
    "una",
    "y",
}


@dataclass(frozen=True, slots=True)
class EstadoClasificacion:
    """Estado único de revisión; los aliases existen solo al exportar el contrato v1."""

    flags: tuple[str, ...] = ()
    exact_duplicate_group: str | None = None
    representative_id: str | None = None
    auto_deduplicated: bool = False
    semantic_duplicate_group: str | None = None
    tool_relevance: str | None = "NOT_APPLICABLE"
    requires_human_decision: bool = True

    @property
    def exact_duplicate(self) -> bool:
        return FLAG_EXACT_DUPLICATE in self.flags

    @property
    def semantic_duplicate(self) -> bool:
        return FLAG_POSSIBLE_SEMANTIC_DUPLICATE in self.flags

    @property
    def suspicious_tool(self) -> bool:
        return self.tool_relevance == "SUSPICIOUS_UNRELATED"

    @property
    def resolution_state(self) -> str:
        if self.auto_deduplicated:
            return "AUTO_DEDUPLICATED"
        return "REQUIRES_HUMAN_DECISION" if self.requires_human_decision else "NOT_ACTIONABLE"

    def a_dict(self) -> dict[str, object]:
        """Serializa todos los aliases públicos históricos sin almacenarlos internamente."""
        return {
            "flags": list(self.flags),
            "duplicado_exacto": self.exact_duplicate,
            "exact_duplicate": self.exact_duplicate,
            "grupo_duplicado_exacto": self.exact_duplicate_group,
            "exact_duplicate_group": self.exact_duplicate_group,
            "exact_duplicate_representative_id": self.representative_id,
            "representative_id": self.representative_id,
            "auto_dedup_representative_id": self.representative_id,
            "auto_dedup_group": self.exact_duplicate_group,
            "representante_duplicado_exacto": bool(
                self.exact_duplicate_group and not self.auto_deduplicated
            ),
            "auto_dedup_representative": bool(
                self.exact_duplicate_group and not self.auto_deduplicated
            ),
            "exact_duplicate_role": (
                "SUPPRESSED"
                if self.auto_deduplicated
                else "REPRESENTATIVE"
                if self.exact_duplicate_group
                else None
            ),
            "auto_deduplicated": self.auto_deduplicated,
            "auto_deduplication_state": ("AUTO_DEDUPLICATED" if self.auto_deduplicated else None),
            "posible_duplicado_semantico": self.semantic_duplicate,
            "semantic_duplicate": self.semantic_duplicate,
            "grupo_duplicado_semantico": self.semantic_duplicate_group,
            "semantic_duplicate_group": self.semantic_duplicate_group,
            "herramienta_no_relacionada": self.suspicious_tool,
            "suspicious_tool": self.suspicious_tool,
            "relevancia_herramienta": self.tool_relevance,
            "tool_relevance": self.tool_relevance,
            "requiere_decision": self.requires_human_decision,
            "clasificacion": {
                "version": "curricular-proposal-classification/v1",
                "flags": list(self.flags),
                "exact_duplicate_group": self.exact_duplicate_group,
                "exact_duplicate_representative_id": self.representative_id,
                "auto_dedup_group": self.exact_duplicate_group,
                "exact_duplicate_role": (
                    "SUPPRESSED"
                    if self.auto_deduplicated
                    else "REPRESENTATIVE"
                    if self.exact_duplicate_group
                    else None
                ),
                "auto_deduplicated": self.auto_deduplicated,
                "resolution_state": self.resolution_state,
                "semantic_duplicate_group": self.semantic_duplicate_group,
                "tool_relevance": self.tool_relevance,
                "auto_deleted": False,
                "auto_merged": False,
                "requires_human_decision": self.requires_human_decision,
            },
        }


def estado_clasificacion(fila: Mapping[str, object]) -> EstadoClasificacion:
    """Convierte filas actuales/legacy: campo canónico anidado > alias inglés > español.

    La precedencia usa presencia, nunca ``or``: False y None explícitos no se
    reemplazan por aliases verdaderos. Un campo ausente se completa desde legacy;
    sin selección de revisión se conserva el default histórico pendiente. Las
    decisiones humanas ADD/KEEP_PENDING/DISCARD no se infieren de estos flags.
    """
    nested = fila.get("clasificacion")
    canonical = nested if isinstance(nested, Mapping) else {}

    def value(key: str, *aliases: str, default: object = None) -> object:
        if key in canonical:
            return canonical[key]
        for alias in aliases:
            if alias in fila:
                return fila[alias]
        return default

    def text(value: object) -> str | None:
        return str(value) if value is not None else None

    exact_group = text(
        value(
            "exact_duplicate_group",
            "exact_duplicate_group",
            "grupo_duplicado_exacto",
            "auto_dedup_group",
        )
    )
    semantic_group = text(
        value("semantic_duplicate_group", "semantic_duplicate_group", "grupo_duplicado_semantico")
    )
    relevance = text(
        value(
            "tool_relevance",
            "tool_relevance",
            "relevancia_herramienta",
            default=(
                "SUSPICIOUS_UNRELATED"
                if value(
                    "suspicious_tool",
                    "suspicious_tool",
                    "herramienta_no_relacionada",
                    default=False,
                )
                else "NOT_APPLICABLE"
            ),
        )
    )
    flags_value = value("flags", "flags")
    if isinstance(flags_value, (list, tuple)):
        flags = tuple(str(flag) for flag in flags_value)
    else:
        flags = tuple(
            flag
            for flag, enabled in (
                (
                    FLAG_EXACT_DUPLICATE,
                    value(
                        "exact_duplicate",
                        "exact_duplicate",
                        "duplicado_exacto",
                        default=bool(exact_group),
                    ),
                ),
                (
                    FLAG_POSSIBLE_SEMANTIC_DUPLICATE,
                    value(
                        "semantic_duplicate",
                        "semantic_duplicate",
                        "posible_duplicado_semantico",
                        default=bool(semantic_group),
                    ),
                ),
                (FLAG_SUSPICIOUS_UNRELATED_TOOL, relevance == "SUSPICIOUS_UNRELATED"),
            )
            if enabled
        )
    return EstadoClasificacion(
        flags=flags,
        exact_duplicate_group=exact_group,
        representative_id=text(
            value(
                "exact_duplicate_representative_id",
                "exact_duplicate_representative_id",
                "representative_id",
                "auto_dedup_representative_id",
            )
        ),
        auto_deduplicated=bool(value("auto_deduplicated", "auto_deduplicated", default=False)),
        semantic_duplicate_group=semantic_group,
        tool_relevance=relevance,
        requires_human_decision=bool(
            value(
                "requires_human_decision",
                "requires_human_decision",
                "requiere_decision",
                default=True,
            )
        ),
    )


def normalizar_texto(valor: object) -> str:
    """Devuelve una clave estable, insensible a acentos y puntuación."""

    texto = unicodedata.normalize("NFKD", str(valor or ""))
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return re.sub(r"[^a-z0-9]+", " ", texto.casefold()).strip()


def clasificar_propuestas(
    propuestas: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Añade flags de revisión sin alterar la identidad ni el orden de las filas.

    Las comparaciones se limitan al mismo tipo curricular. Los grupos se
    identifican con hashes de contenido para que el resultado sea reproducible
    entre procesos y ejecuciones, aun cuando las filas lleguen en otro orden.
    """

    resultado = [dict(fila) for fila in propuestas]
    nombres = {indice: normalizar_texto(_nombre(fila)) for indice, fila in enumerate(resultado)}
    tipos = {indice: normalizar_texto(fila.get("tipo")) for indice, fila in enumerate(resultado)}

    # Exact names are only aliases inside the same source package.  A course,
    # syllabus, execution or source skill with the same label is a different
    # audit unit and must remain independently decidable.
    exact_groups: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for indice, clave in nombres.items():
        if clave:
            exact_groups[(_alcance_fila(resultado[indice]), tipos[indice], clave)].append(indice)

    exact_ids: dict[int, str] = {}
    exact_representatives: dict[int, str] = {}
    auto_deduplicated: set[int] = set()
    for (_alcance, tipo, clave), indices in sorted(exact_groups.items()):
        if len(indices) < 2:
            continue
        grupo = _grupo("EXACT", tipo, clave)
        representante = _representante_exacto(indices, resultado)
        representante_id = _id_estable(resultado[representante], tipo, clave)
        for indice in indices:
            exact_ids[indice] = grupo
            exact_representatives[indice] = representante_id
            if indice != representante:
                auto_deduplicated.add(indice)

    semantic_edges: dict[int, set[int]] = defaultdict(set)
    for left in range(len(resultado)):
        if not nombres[left]:
            continue
        for right in range(left + 1, len(resultado)):
            if not nombres[right] or tipos[left] != tipos[right]:
                continue
            if _alcance_fila(resultado[left]) != _alcance_fila(resultado[right]):
                continue
            if (tipos[left], nombres[left]) == (tipos[right], nombres[right]):
                continue
            if _posible_equivalencia(nombres[left], nombres[right]):
                semantic_edges[left].add(right)
                semantic_edges[right].add(left)

    semantic_ids: dict[int, str] = {}
    for indices in _componentes(semantic_edges):
        if len(indices) < 2:
            continue
        firma = sorted(
            (
                _alcance_fila(resultado[indice]),
                tipos[indice],
                nombres[indice],
                _id_fila(resultado[indice]),
            )
            for indice in indices
        )
        grupo = _grupo("SEMANTIC", *("|".join(partes) for partes in firma))
        for indice in indices:
            semantic_ids[indice] = grupo

    for indice, fila in enumerate(resultado):
        flags: list[str] = []
        grupo_exacto = exact_ids.get(indice)
        grupo_semantico = semantic_ids.get(indice)
        es_auto_deduplicada = indice in auto_deduplicated
        if grupo_exacto:
            flags.append(FLAG_EXACT_DUPLICATE)
        if grupo_semantico:
            flags.append(FLAG_POSSIBLE_SEMANTIC_DUPLICATE)

        relevancia = "NOT_APPLICABLE"
        herramienta_no_relacionada = False
        if tipos[indice] == "herramienta":
            relevancia = _relevancia_herramienta(fila, nombres[indice])
            herramienta_no_relacionada = relevancia == "SUSPICIOUS_UNRELATED"
            if herramienta_no_relacionada:
                flags.append(FLAG_SUSPICIOUS_UNRELATED_TOOL)

        if es_auto_deduplicada:
            estado_anterior = str(fila.get("estado_resolucion") or "").strip()
            if estado_anterior and estado_anterior != "AUTO_DEDUPLICADA":
                fila.setdefault("estado_resolucion_original", estado_anterior)
            fila["estado_resolucion"] = "AUTO_DEDUPLICADA"
        elif fila.get("estado_resolucion") == "AUTO_DEDUPLICADA":
            estado_original = str(fila.get("estado_resolucion_original") or "").strip()
            if estado_original:
                fila["estado_resolucion"] = estado_original

        estado = EstadoClasificacion(
            flags=tuple(flags),
            exact_duplicate_group=grupo_exacto,
            representative_id=exact_representatives.get(indice),
            auto_deduplicated=es_auto_deduplicada,
            semantic_duplicate_group=grupo_semantico,
            tool_relevance=relevancia,
            requires_human_decision=propuesta_estructurada(fila) and not es_auto_deduplicada,
        )
        fila.update(estado.a_dict())
    return resultado


def propuesta_estructurada(fila: dict[str, object]) -> bool:
    """Indica si una fila contiene una propuesta estructurada."""

    propuesta = fila.get("propuesta")
    if not isinstance(propuesta, dict):
        return False
    return bool(normalizar_texto(propuesta.get("nombre") or propuesta.get("id")))


def puede_recibir_decision(fila: dict[str, object]) -> bool:
    """Indica si una fila puede entrar en la cola ``ADD``/``KEEP_PENDING``."""

    return propuesta_estructurada(fila) and not estado_clasificacion(fila).auto_deduplicated


def requiere_resolucion_curricular(fila: dict[str, object]) -> bool:
    """Indica si una fila sigue bloqueando la publicación curricular.

    La cola puede contener evidencia sin una propuesta estructurada, por
    ejemplo cuando el análisis LLM no estuvo disponible. Esa fila no puede
    recibir ``ADD`` todavía, pero tampoco puede tratarse como resuelta: si se
    ignora aquí, los CSV canónicos se materializan antes del HITL.
    """

    if estado_clasificacion(fila).auto_deduplicated:
        return False
    decision = str(fila.get("decision") or "").strip().upper()
    if decision in {"ADD", "DISCARD"}:
        return False
    if decision == "KEEP_PENDING":
        # HITL explicitly reviewed the evidence and chose not to promote it.
        # It remains visible as retained evidence, but it must not block the
        # already-decided canonical rows from being materialized.
        return False
    estado = str(fila.get("estado_resolucion") or "").strip().upper()
    return (
        not decision or estado in _UNRESOLVED_RESOLUTION_STATES or estado.startswith("PENDIENTE_")
    )


def resumen_clasificacion(propuestas: list[dict[str, object]]) -> dict[str, int]:
    """Cuenta señales para el resumen público del checkpoint."""

    estados = [estado_clasificacion(fila) for fila in propuestas]
    return {
        "exact_duplicate_rows": sum(estado.exact_duplicate for estado in estados),
        "semantic_duplicate_rows": sum(estado.semantic_duplicate for estado in estados),
        "suspicious_unrelated_tool_rows": sum(estado.suspicious_tool for estado in estados),
        "exact_duplicate_groups": len(
            {estado.exact_duplicate_group for estado in estados if estado.exact_duplicate_group}
        ),
        "semantic_duplicate_groups": len(
            {
                estado.semantic_duplicate_group
                for estado in estados
                if estado.semantic_duplicate_group
            }
        ),
        "auto_deduplicated_rows": sum(estado.auto_deduplicated for estado in estados),
        "auto_deduplicated_groups": len(
            {
                estado.exact_duplicate_group
                for estado in estados
                if estado.auto_deduplicated and estado.exact_duplicate_group
            }
        ),
    }


def _nombre(fila: dict[str, object]) -> object:
    propuesta = fila.get("propuesta")
    if isinstance(propuesta, dict):
        return propuesta.get("nombre") or propuesta.get("id") or ""
    return fila.get("nombre") or fila.get("nombre_propuesta") or ""


def _id_fila(fila: dict[str, object]) -> str:
    return str(fila.get("id_pendiente") or "")


def _alcance_fila(fila: dict[str, object]) -> str:
    """Return a stable source scope for deduplication, never a global name key."""

    identity = fila.get("source_identity")
    if isinstance(identity, dict):
        values = {
            key: str(identity.get(key) or "")
            for key in (
                "id_ejecucion",
                "carrera",
                "periodo",
                "id_curso",
                "id_silabo",
                "id_habilidad_fuente",
            )
        }
    else:
        values = {
            "id_ejecucion": str(fila.get("id_ejecucion") or fila.get("execution_id") or ""),
            "carrera": str(fila.get("carrera") or fila.get("career") or ""),
            "periodo": str(fila.get("periodo") or fila.get("period") or ""),
            "id_curso": str(fila.get("id_curso") or fila.get("course_id") or ""),
            "id_silabo": str(
                fila.get("id_silabo") or fila.get("syllabus_id") or fila.get("silabo") or ""
            ),
            "id_habilidad_fuente": str(
                fila.get("id_habilidad_fuente") or fila.get("source_skill_id") or ""
            ),
        }
    package_id = str(fila.get("id_paquete_chh") or fila.get("package_id") or "")
    values["package_id"] = package_id
    return json.dumps(values, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _representante_exacto(indices: list[int], propuestas: list[dict[str, object]]) -> int:
    """Choose a representative without relying on the input order.

    A numeric confidence is strongest evidence when present. Ties then use the
    count and normalized length of non-empty evidence, followed by the stable
    pending id. Missing confidence is weaker than any numeric confidence.
    """

    return min(
        indices,
        key=lambda indice: (
            -_confianza(propuestas[indice]),
            -_fuerza_evidencia(propuestas[indice])[0],
            -_fuerza_evidencia(propuestas[indice])[1],
            _id_estable(propuestas[indice], "", ""),
        ),
    )


def _confianza(fila: dict[str, object]) -> float:
    valor = fila.get("confianza")
    if valor is None:
        return -1.0
    try:
        numero = float(str(valor))
    except (TypeError, ValueError):
        return -1.0
    return numero if math.isfinite(numero) else -1.0


def _fuerza_evidencia(fila: dict[str, object]) -> tuple[int, int]:
    evidencia = fila.get("evidencia")
    valores = evidencia if isinstance(evidencia, (list, tuple, set)) else [evidencia]
    normalizadas = [normalizar_texto(valor) for valor in valores if normalizar_texto(valor)]
    return len(normalizadas), sum(len(valor) for valor in normalizadas)


def _id_estable(fila: dict[str, object], tipo: str, clave: str) -> str:
    identificador = _id_fila(fila)
    if identificador:
        return identificador
    partes = "|".join(
        f"{normalizar_texto(llave)}={normalizar_texto(valor)}"
        for llave, valor in sorted(fila.items(), key=lambda item: str(item[0]))
        if llave not in {"clasificacion", "flags"}
    )
    return _grupo("ROW", tipo, clave, partes)


def _grupo(prefijo: str, *partes: str) -> str:
    payload = "|".join(partes).encode("utf-8")
    return f"{prefijo}_{hashlib.sha256(payload).hexdigest()[:16]}"


def _tokens(clave: str) -> set[str]:
    return {token for token in clave.split() if len(token) > 2 and token not in _STOPWORDS}


def _posible_equivalencia(left: str, right: str) -> bool:
    tokens_left = _tokens(left)
    tokens_right = _tokens(right)
    comunes = tokens_left & tokens_right
    if not comunes:
        return False
    union = tokens_left | tokens_right
    jaccard = len(comunes) / len(union) if union else 0.0
    ratio = SequenceMatcher(None, left, right, autojunk=False).ratio()
    return (len(comunes) >= 2 and jaccard >= 0.5) or ratio >= 0.76


def _componentes(grafo: dict[int, set[int]]) -> list[list[int]]:
    visitados: set[int] = set()
    componentes: list[list[int]] = []
    for inicio in sorted(grafo):
        if inicio in visitados:
            continue
        pendientes = [inicio]
        visitados.add(inicio)
        componente: list[int] = []
        while pendientes:
            actual = pendientes.pop()
            componente.append(actual)
            for siguiente in sorted(grafo.get(actual, ())):
                if siguiente not in visitados:
                    visitados.add(siguiente)
                    pendientes.append(siguiente)
        componentes.append(sorted(componente))
    return componentes


def _relevancia_herramienta(fila: dict[str, object], nombre: str) -> str:
    propuesta = fila.get("propuesta")
    descripcion = propuesta.get("descripcion") if isinstance(propuesta, dict) else ""
    evidencia = fila.get("evidencia")
    valores_evidencia = evidencia if isinstance(evidencia, list) else [evidencia]
    partes = [str(valor or "") for valor in valores_evidencia if valor]
    partes.extend(
        str(valor or "")
        for valor in (
            fila.get("descripcion_fuente"),
            fila.get("seccion_fuente"),
            descripcion,
        )
        if valor
    )
    texto = normalizar_texto(" ".join(partes))
    if not nombre or not texto:
        return "SUSPICIOUS_UNRELATED"
    tokens_nombre = _tokens(nombre)
    tokens_texto = _tokens(texto)
    if not tokens_nombre:
        return "SUSPICIOUS_UNRELATED"
    cobertura = len(tokens_nombre & tokens_texto) / len(tokens_nombre)
    return "RELEVANT" if cobertura >= 0.5 or nombre in texto else "SUSPICIOUS_UNRELATED"
