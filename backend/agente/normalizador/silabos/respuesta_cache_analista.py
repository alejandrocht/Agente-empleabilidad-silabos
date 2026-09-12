"""Normalización determinista de respuestas y persistencia de cache del analista."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import TypeVar

TDecision = TypeVar("TDecision")
TResultado = TypeVar("TResultado")


def _asignar_decisiones_por_orden(
    lote: tuple[dict[str, object], ...],
    respuesta: object,
    *,
    materializar_decision: Callable[[Mapping[str, object], TDecision], TResultado | None],
) -> list[TResultado]:
    """Restaura el linaje interno usando el orden estable de entrada/salida."""

    decisiones_respuesta = getattr(respuesta, "decisiones")
    _validar_respuesta_por_orden(
        lote,
        decisiones_respuesta,
        exigir_logro=True,
        nombre="decisiones",
    )
    decisiones: list[TResultado] = []
    for caso, decision in zip(lote, decisiones_respuesta, strict=True):
        materializada = materializar_decision(caso, decision)
        if materializada is not None:
            decisiones.append(materializada)
    return decisiones


def _asignar_decisiones_parciales_por_logro(
    lote: tuple[dict[str, object], ...],
    respuesta: object,
    *,
    materializar_decision: Callable[[Mapping[str, object], TDecision], TResultado | None],
) -> list[TResultado]:
    """Mapea una respuesta parcial solo si cada logro literal identifica su caso."""

    casos_por_logro: dict[str, dict[str, object]] = {}
    for caso in lote:
        clave = _clave_logro_literal(caso.get("logro"))
        if not clave or clave in casos_por_logro:
            raise ValueError("No se puede identificar de forma única un logro del lote.")
        casos_por_logro[clave] = caso

    decisiones: list[TResultado] = []
    claves_usadas: set[str] = set()
    for decision in getattr(respuesta, "decisiones"):
        clave = _clave_logro_literal(getattr(decision, "logro"))
        caso = casos_por_logro.get(clave)
        if caso is None or clave in claves_usadas:
            raise ValueError("La respuesta parcial contiene un logro ausente o duplicado del lote.")
        claves_usadas.add(clave)
        materializada = materializar_decision(caso, decision)
        if materializada is not None:
            decisiones.append(materializada)
    return decisiones


def _validar_respuesta_por_orden(
    lote: tuple[dict[str, object], ...],
    respuesta: Iterable[object],
    *,
    exigir_logro: bool,
    nombre: str,
) -> None:
    """Evita asignar una respuesta LLM a un ID distinto por omisión o reordenamiento."""

    respuestas = tuple(respuesta)
    if len(respuestas) != len(lote):
        raise ValueError(
            f"La cardinalidad de la respuesta de {nombre} es {len(respuestas)} "
            f"elementos para {len(lote)} casos."
        )

    logros_respuesta = [str(getattr(item, "logro", "") or "").strip() for item in respuestas]
    for indice, (caso, logro_respuesta) in enumerate(zip(lote, logros_respuesta, strict=True), 1):
        logro_esperado = str(caso.get("logro") or "").strip()
        if not logro_respuesta:
            raise ValueError(
                f"La respuesta de {nombre} no devolvió el logro literal del caso {indice}."
            )
        if _clave_logro_literal(logro_respuesta) != _clave_logro_literal(logro_esperado):
            raise ValueError(f"La respuesta de {nombre} no conserva el orden del caso {indice}.")


def _clave_logro_literal(valor: object) -> str:
    """Normaliza únicamente Unicode y espacios; conserva puntuación y palabras."""

    texto = unicodedata.normalize("NFKC", str(valor or "")).replace(" ", " ")
    return re.sub(r"\s+", " ", texto).strip().casefold()


def _clave_lote(
    lote: tuple[dict[str, object], ...],
    perfil: dict[str, object],
    modelo: str,
    version_prompt: str = "",
) -> str:
    payload = json.dumps(
        {"lote": lote, "perfil": perfil, "modelo": modelo, "version_prompt": version_prompt},
        ensure_ascii=False,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _leer_cache(ruta: Path) -> dict[str, dict[str, object]]:
    if not ruta.is_file():
        return {}
    resultado: dict[str, dict[str, object]] = {}
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        try:
            fila = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if isinstance(fila, dict) and isinstance(fila.get("clave_lote"), str):
            respuesta = fila.get("respuesta")
            if isinstance(respuesta, dict):
                resultado[fila["clave_lote"]] = respuesta
    return resultado


def _guardar_cache(ruta: Path, cache: dict[str, dict[str, object]]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8", newline="\n") as archivo:
        for clave, respuesta in sorted(cache.items()):
            archivo.write(
                json.dumps(
                    {"clave_lote": clave, "respuesta": respuesta},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                + "\n"
            )


def _nombre_modelo(llm: object) -> str:
    for atributo in ("model_name", "model"):
        valor = getattr(llm, atributo, "")
        if valor:
            return str(valor)
    return "desconocido"
