"""Política determinista de herramientas compartida por análisis y salida curricular."""

from __future__ import annotations

from agente.normalizador.empleabilidad.catalogo import clave_concepto

_HERRAMIENTAS_GENERICAS = {
    "herramientas",
    "herramientas digitales",
    "herramientas disruptivas",
    "recursos",
    "recursos de aprendizaje",
}
_CONCEPTOS_CURRICULARES_NO_HERRAMIENTA = {
    "etl",
    "sql",
    "cubo",
    "cubos",
    "kpi",
    "bsc",
}
_ALIASES_CERRADOS_HERRAMIENTAS: dict[str, frozenset[str]] = {
    "excel": frozenset(("excel", "microsoft excel", "ms excel")),
    "microsoft excel": frozenset(("excel", "microsoft excel", "ms excel")),
    "ms excel": frozenset(("excel", "microsoft excel", "ms excel")),
    "word": frozenset(("word", "microsoft word", "ms word")),
    "microsoft word": frozenset(("word", "microsoft word", "ms word")),
    "ms word": frozenset(("word", "microsoft word", "ms word")),
    "google analytics": frozenset(("google analytics", "google analytics 4")),
    "google analytics 4": frozenset(("google analytics", "google analytics 4")),
}
_NOMBRES_CANONICOS_HERRAMIENTAS = {
    "excel": "Microsoft Excel",
    "microsoft excel": "Microsoft Excel",
    "ms excel": "Microsoft Excel",
    "word": "Microsoft Word",
    "microsoft word": "Microsoft Word",
    "ms word": "Microsoft Word",
    "google analytics": "Google Analytics",
    "google analytics 4": "Google Analytics",
}


def es_herramienta_concreta(nombre: str) -> bool:
    """No reetiqueta procesos, lenguajes, modelos o métricas como software."""

    return clave_concepto(nombre) not in _CONCEPTOS_CURRICULARES_NO_HERRAMIENTA


def nombre_herramienta_coincide(nombre: str, disponibles: set[str]) -> bool:
    """Acepta solo el nombre detectado o aliases gráficos inocuos."""

    clave = clave_concepto(nombre)
    return bool(_claves_herramienta_cerradas(clave) & disponibles)


def _claves_herramienta_cerradas(nombre: str) -> frozenset[str]:
    """Devuelve el nombre normalizado y solo sus aliases explícitamente aprobados."""

    clave = clave_concepto(nombre)
    if not clave:
        return frozenset()
    return _ALIASES_CERRADOS_HERRAMIENTAS.get(clave, frozenset((clave,)))


def nombre_herramienta_canonico(nombre: str) -> str:
    """Resuelve únicamente aliases cerrados al nombre canónico de publicación."""

    clave = clave_concepto(nombre)
    return _NOMBRES_CANONICOS_HERRAMIENTAS.get(clave, nombre.strip())


def clave_herramienta_canonica(nombre: str) -> str:
    """Produce una clave de deduplicación común para nombre canónico y aliases cerrados."""

    return clave_concepto(nombre_herramienta_canonico(nombre))


def coincide_nombre_herramienta_en_texto(nombre: str, texto: str) -> bool:
    """Exige el nombre canónico o un alias cerrado como frase normalizada completa."""

    texto_normalizado = clave_concepto(texto).strip(".,;:!?")
    return any(
        f" {clave} " in f" {texto_normalizado} " for clave in _claves_herramienta_cerradas(nombre)
    )


def herramienta_nueva_evidenciada(
    nombre: str,
    _evidencia_llm: str,
    caso: dict[str, object],
) -> bool:
    """Allows a new tool only when the source program names it literally."""

    clave_nombre = clave_concepto(nombre)
    if (
        not clave_nombre
        or clave_nombre in _HERRAMIENTAS_GENERICAS
        or clave_nombre in _CONCEPTOS_CURRICULARES_NO_HERRAMIENTA
    ):
        return False
    evidencias = caso.get("evidencia_herramientas_candidata")
    if evidencias is None:
        evidencias = caso.get("evidencia_herramientas")
    if not isinstance(evidencias, list):
        return False
    for item in evidencias:
        if not isinstance(item, dict):
            continue
        texto = str(item.get("texto") or "")
        texto_minusculas = texto.lower()
        clave_texto = clave_concepto(texto)
        if (
            item.get("origen") == "programa_analitico"
            and item.get("seccion") == "programa_analitico"
            and "bibliografia" not in clave_texto
            and not any(url in texto_minusculas for url in ("http://", "https://", "www."))
            and coincide_nombre_herramienta_en_texto(nombre, texto)
        ):
            return True
    return False
