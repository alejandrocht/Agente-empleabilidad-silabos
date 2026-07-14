"""Única fuente de reglas para aceptar exclusivamente Cypher de lectura.

La guarda se aplica en el nodo de validación y otra vez justo antes de ejecutar la transacción.
Así un uso directo del cliente Neo4j tampoco puede saltarse el bloqueo de escrituras.
"""

from __future__ import annotations

import re

# Se usa ``frozenset`` porque estas reglas son constantes de seguridad del proceso.
PALABRAS_BLOQUEADAS: frozenset[str] = frozenset(
    {
        "create",
        "merge",
        "delete",
        "detach",
        "set",
        "remove",
        "drop",
        "load",
        "periodic",
        "dbms",
        "constraint",
        "index",
        "foreach",
        "show",
        "grant",
        "deny",
        "revoke",
    }
)
INICIOS_PERMITIDOS = ("match", "with", "return", "call db.", "call apoc.meta")
_CALLS_LECTURA = (
    "call db.labels",
    "call db.relationshiptypes",
    "call db.propertykeys",
    "call db.schema.",
    "call apoc.meta.",
)


def validar_seguridad_basica(cypher: str) -> list[str]:
    """Devuelve problemas de solo lectura que pueden verificarse sin tocar Neo4j."""
    problemas: list[str] = []
    plano = re.sub(r"\s+", " ", (cypher or "").lower()).strip()
    if not plano:
        return ["la consulta está vacía"]

    # Solo se admite un statement; un punto y coma final se tolera, pero no consultas apiladas.
    sin_final = plano[:-1].rstrip() if plano.endswith(";") else plano
    if ";" in sin_final:
        problemas.append("no se permiten múltiples consultas")
    if not plano.startswith(INICIOS_PERMITIDOS):
        problemas.append("la consulta no empieza como lectura segura")

    # Se bloquean tokens completos para no confundir fragmentos de nombres de propiedades.
    palabras = set(re.findall(r"[a-zA-Z_]+", plano))
    bloqueadas = sorted(palabras & PALABRAS_BLOQUEADAS)
    if bloqueadas:
        problemas.append(f"operaciones no permitidas: {', '.join(bloqueadas)}")

    # Cada ``CALL`` se limita a procedimientos de metadatos conocidos como lectura, incluso
    # cuando aparece después de MATCH o WITH.
    for procedimiento in re.findall(r"\bcall\s+([a-zA-Z0-9_.]+)", plano):
        llamada = f"call {procedimiento}"
        if not llamada.startswith(_CALLS_LECTURA):
            problemas.append("el procedimiento CALL no está en la lista de solo lectura")
            break
    return problemas


def _elementos_schema(cypher: str) -> tuple[set[str], set[str]]:
    """Extrae labels y tipos de relación usados por patrones Cypher sencillos."""
    relaciones: set[str] = set()
    for bloque in re.findall(r"\[[^\]]*\]", cypher):
        coincidencia = re.search(r":\s*([\w|`Ññ]+)", bloque)
        if coincidencia:
            relaciones.update(
                token.strip("`").strip()
                for token in coincidencia.group(1).split("|")
                if token.strip("`").strip()
            )

    labels: set[str] = set()
    for bloque in re.findall(r"\(\s*\w*\s*:\s*([\w:`Ññ]+)", cypher):
        labels.update(token.strip("`").strip() for token in bloque.split(":") if token.strip())
    return labels, relaciones


def _patrones_schema(cypher: str) -> set[tuple[str, str, str]]:
    """Extrae triples label-relación-label de patrones explícitos y simples."""
    nodo = r"\(\s*(?:`?\w+`?)?\s*:\s*`?([\wÑñ]+)`?[^)]*\)"
    relacion = r"\[\s*(?:`?\w+`?)?\s*:\s*([\wÑñ`|]+)[^]]*\]"
    patron = re.compile(rf"{nodo}\s*<?-\s*{relacion}\s*-?>?\s*{nodo}")
    triples: set[tuple[str, str, str]] = set()
    for coincidencia in patron.finditer(cypher):
        origen, tipos, destino = coincidencia.groups()
        for tipo in tipos.split("|"):
            if limpio := tipo.strip("` "):
                triples.add((origen, limpio, destino))
    return triples


def validar_consulta(cypher: str) -> str | None:
    """Valida seguridad, schema vivo y sintaxis mediante ``EXPLAIN`` sin ejecutar datos."""
    problemas = validar_seguridad_basica(cypher)
    if problemas:
        return "Cypher inválido: " + " | ".join(problemas)

    # Los imports locales evitan que el cliente y su defensa en profundidad formen un ciclo.
    from agente_ciar.db.neo4j import introspeccionar_schema, validar_sintaxis

    intro = introspeccionar_schema()
    labels_usados, relaciones_usadas = _elementos_schema(cypher)
    labels_conocidos = set(intro["labels"])
    relaciones_conocidas = {item["rel"] for item in intro["topology"]}
    topologia_conocida = {
        (item["src"], item["rel"], item["tgt"]) for item in intro["topology"]
    }
    topologia_conocida |= {
        (destino, relacion, origen) for origen, relacion, destino in topologia_conocida
    }

    labels_inventados = sorted(labels_usados - labels_conocidos)
    relaciones_inventadas = sorted(relaciones_usadas - relaciones_conocidas)
    if labels_inventados:
        problemas.append(f"labels inventados {labels_inventados}")
    if relaciones_inventadas:
        problemas.append(f"relaciones inventadas {relaciones_inventadas}")

    patrones_inventados = sorted(_patrones_schema(cypher) - topologia_conocida)
    if patrones_inventados:
        detalle = [f"(:{src})-[:{rel}]-(:{tgt})" for src, rel, tgt in patrones_inventados]
        problemas.append(f"conexiones inexistentes {detalle}")

    # Las búsquedas por nombre ocurren solo en el resolver de entidades parametrizado.
    if re.search(r"\bCONTAINS\b", cypher, re.IGNORECASE):
        problemas.append("CONTAINS no permitido en el Cypher final")
    if re.search(r"\bnombre_norm\b", cypher, re.IGNORECASE):
        problemas.append("nombre_norm no permitido en el Cypher final")
    if "->" in cypher or "<-" in cypher:
        problemas.append("las relaciones deben escribirse sin dirección")
    if problemas:
        return "Cypher inválido: " + " | ".join(problemas)

    error_sintaxis = validar_sintaxis(cypher)
    if error_sintaxis:
        return "Cypher con error de sintaxis: " + error_sintaxis
    return None
