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
from difflib import SequenceMatcher

FLAG_EXACT_DUPLICATE = "EXACT_DUPLICATE"
FLAG_POSSIBLE_SEMANTIC_DUPLICATE = "POSSIBLE_SEMANTIC_DUPLICATE"
FLAG_SUSPICIOUS_UNRELATED_TOOL = "SUSPICIOUS_UNRELATED_TOOL"

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

        requiere_decision = propuesta_estructurada(fila) and not es_auto_deduplicada
        estado_clasificacion = (
            "AUTO_DEDUPLICATED"
            if es_auto_deduplicada
            else "REQUIRES_HUMAN_DECISION"
            if requiere_decision
            else "NOT_ACTIONABLE"
        )

        # Estos campos son redundantes deliberadamente: el frontend puede usar
        # los nombres en español y los consumidores de auditoría los nombres
        # estables en inglés sin recalcular las señales.
        fila.update(
            {
                "flags": flags,
                "duplicado_exacto": bool(grupo_exacto),
                "exact_duplicate": bool(grupo_exacto),
                "grupo_duplicado_exacto": grupo_exacto,
                "exact_duplicate_group": grupo_exacto,
                "exact_duplicate_representative_id": exact_representatives.get(indice),
                "representative_id": exact_representatives.get(indice),
                "auto_dedup_representative_id": exact_representatives.get(indice),
                "auto_dedup_group": grupo_exacto,
                "representante_duplicado_exacto": bool(grupo_exacto and not es_auto_deduplicada),
                "auto_dedup_representative": bool(grupo_exacto and not es_auto_deduplicada),
                "exact_duplicate_role": (
                    "SUPPRESSED"
                    if es_auto_deduplicada
                    else "REPRESENTATIVE"
                    if grupo_exacto
                    else None
                ),
                "auto_deduplicated": es_auto_deduplicada,
                "auto_deduplication_state": ("AUTO_DEDUPLICATED" if es_auto_deduplicada else None),
                "posible_duplicado_semantico": bool(grupo_semantico),
                "semantic_duplicate": bool(grupo_semantico),
                "grupo_duplicado_semantico": grupo_semantico,
                "semantic_duplicate_group": grupo_semantico,
                "herramienta_no_relacionada": herramienta_no_relacionada,
                "suspicious_tool": herramienta_no_relacionada,
                "relevancia_herramienta": relevancia,
                "tool_relevance": relevancia,
                "requiere_decision": requiere_decision,
                "clasificacion": {
                    "version": "curricular-proposal-classification/v1",
                    "flags": list(flags),
                    "exact_duplicate_group": grupo_exacto,
                    "exact_duplicate_representative_id": exact_representatives.get(indice),
                    "auto_dedup_group": grupo_exacto,
                    "exact_duplicate_role": (
                        "SUPPRESSED"
                        if es_auto_deduplicada
                        else "REPRESENTATIVE"
                        if grupo_exacto
                        else None
                    ),
                    "auto_deduplicated": es_auto_deduplicada,
                    "resolution_state": estado_clasificacion,
                    "semantic_duplicate_group": grupo_semantico,
                    "tool_relevance": relevancia,
                    "auto_deleted": False,
                    "auto_merged": False,
                    "requires_human_decision": requiere_decision,
                },
            }
        )
    return resultado


def propuesta_estructurada(fila: dict[str, object]) -> bool:
    """Indica si una fila contiene una propuesta estructurada."""

    propuesta = fila.get("propuesta")
    if not isinstance(propuesta, dict):
        return False
    return bool(normalizar_texto(propuesta.get("nombre") or propuesta.get("id")))


def puede_recibir_decision(fila: dict[str, object]) -> bool:
    """Indica si una fila puede entrar en la cola ``ADD``/``KEEP_PENDING``."""

    return propuesta_estructurada(fila) and not bool(fila.get("auto_deduplicated"))


def resumen_clasificacion(propuestas: list[dict[str, object]]) -> dict[str, int]:
    """Cuenta señales para el resumen público del checkpoint."""

    return {
        "exact_duplicate_rows": sum(bool(fila.get("duplicado_exacto")) for fila in propuestas),
        "semantic_duplicate_rows": sum(
            bool(fila.get("posible_duplicado_semantico")) for fila in propuestas
        ),
        "suspicious_unrelated_tool_rows": sum(
            bool(fila.get("herramienta_no_relacionada")) for fila in propuestas
        ),
        "exact_duplicate_groups": len(
            {
                fila.get("grupo_duplicado_exacto")
                for fila in propuestas
                if fila.get("grupo_duplicado_exacto")
            }
        ),
        "semantic_duplicate_groups": len(
            {
                fila.get("grupo_duplicado_semantico")
                for fila in propuestas
                if fila.get("grupo_duplicado_semantico")
            }
        ),
        "auto_deduplicated_rows": sum(bool(fila.get("auto_deduplicated")) for fila in propuestas),
        "auto_deduplicated_groups": len(
            {
                fila.get("grupo_duplicado_exacto")
                for fila in propuestas
                if fila.get("auto_deduplicated") and fila.get("grupo_duplicado_exacto")
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
    if not isinstance(valor, (str, int, float)):
        return -1.0
    try:
        numero = float(valor)
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
            fila.get("etiqueta_logro"),
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
