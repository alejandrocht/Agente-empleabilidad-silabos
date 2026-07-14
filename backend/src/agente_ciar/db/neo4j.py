"""Cliente Neo4j de solo lectura e introspección del schema vivo."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from neo4j import READ_ACCESS, GraphDatabase

from agente_ciar.config.settings import texto


def _sesion_kwargs() -> dict[str, Any]:
    """Centraliza el modo de acceso y la base opcional usados por todas las sesiones."""
    argumentos: dict[str, Any] = {"default_access_mode": READ_ACCESS}
    database = texto("NEO4J_DATABASE")
    if database:
        argumentos["database"] = database
    return argumentos


@lru_cache(maxsize=1)
def obtener_driver() -> Any:
    """Crea y verifica una única conexión con las credenciales del entorno."""
    uri = texto("NEO4J_URI", "neo4j://127.0.0.1:7687")
    usuario = texto("NEO4J_USER", "neo4j")
    contrasena = texto("NEO4J_PASSWORD")
    driver = GraphDatabase.driver(uri, auth=(usuario, contrasena))
    driver.verify_connectivity()
    return driver


@lru_cache(maxsize=1)
def introspeccionar_schema() -> dict[str, Any]:
    """Descubre labels, propiedades, relaciones y muestras reales una vez por proceso."""
    with obtener_driver().session(**_sesion_kwargs()) as sesion:
        # Los labels y sus conteos permiten validar consultas y describir el grafo al LLM.
        conteo_por_label = {
            registro["label"]: registro["total"]
            for registro in sesion.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS total ORDER BY total DESC"
            )
            if registro["label"]
        }
        if not conteo_por_label:
            raise RuntimeError("Neo4j está vacío: carga los datos antes de iniciar el agente")

        # Las propiedades se consultan desde el procedimiento de schema de Neo4j.
        props_por_label: dict[str, list[str]] = {}
        for registro in sesion.run(
            "CALL db.schema.nodeTypeProperties() YIELD nodeLabels, propertyName "
            "RETURN nodeLabels[0] AS label, collect(DISTINCT propertyName) AS props"
        ):
            if registro["label"]:
                props_por_label[registro["label"]] = sorted(registro["props"])

        # La topología se deriva de relaciones realmente almacenadas. ``db.schema.visualization``
        # combina labels de nodos con tipos de relación y puede producir pares que no existen.
        topologia: list[dict[str, Any]] = []
        for registro in sesion.run(
            "MATCH (origen)-[rel]->(destino) "
            "RETURN labels(origen)[0] AS src, type(rel) AS tipo_rel, "
            "labels(destino)[0] AS tgt, count(rel) AS freq "
            "ORDER BY freq DESC"
        ):
            topologia.append(
                {
                    "src": registro["src"],
                    "rel": registro["tipo_rel"],
                    "tgt": registro["tgt"],
                    "freq": registro["freq"],
                }
            )

        # Se detectan las propiedades visibles de nombre sin depender de ``nombre_norm``.
        nombres_por_label: dict[str, str] = {}
        for label, propiedades in props_por_label.items():
            if "nombre" in propiedades:
                nombres_por_label[label] = "nombre"
                continue
            for propiedad in propiedades:
                if propiedad.startswith("nombre_") and propiedad != "nombre_norm":
                    nombres_por_label[label] = propiedad
                    break

        # Cinco ejemplos por label ayudan a reducir alucinaciones en el flujo dinámico.
        ejemplos: dict[str, list[str]] = {}
        for label, propiedad in nombres_por_label.items():
            consulta = (
                f"MATCH (n:`{label}`) WHERE n.`{propiedad}` IS NOT NULL "
                f"RETURN n.`{propiedad}` AS muestra LIMIT 5"
            )
            valores = [fila["muestra"] for fila in sesion.run(consulta) if fila["muestra"]]
            if valores:
                ejemplos[label] = valores

    return {
        "labels": conteo_por_label,
        "props": props_por_label,
        "topology": topologia,
        "samples": ejemplos,
        "name_props": nombres_por_label,
    }


def construir_schema_texto() -> str:
    """Convierte la introspección en instrucciones compactas para generar Cypher válido."""
    intro = introspeccionar_schema()
    lineas = [
        "ONTOLOGÍA CIAR EN NEO4J (descubierta en vivo)",
        "Usa exactamente estos labels, relaciones y propiedades.",
        "",
        "NODOS (label, conteo, propiedades)",
    ]

    for label, total in intro["labels"].items():
        propiedades = intro["props"].get(label, [])
        nombre = intro["name_props"].get(label)
        marca = f" [NOMBRE = {nombre}]" if nombre else ""
        lineas.append(f"- :{label} ({total}) props: {', '.join(propiedades)}{marca}")

    lineas.extend(["", "RELACIONES (usar sin dirección)"])
    for item in intro["topology"]:
        lineas.append(f"- (:{item['src']})-[:{item['rel']}]-(:{item['tgt']})")

    if intro["samples"]:
        lineas.extend(["", "EJEMPLOS REALES"])
        for label, nombres in intro["samples"].items():
            lineas.append(f"- {label}: {', '.join(nombres)}")
    return "\n".join(lineas)


def ejecutar_lectura(cypher: str, parametros: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Vuelve a comprobar la guarda y ejecuta el statement en una transacción de lectura."""
    from agente_ciar.guardas.cypher import validar_seguridad_basica

    problemas = validar_seguridad_basica(cypher)
    if problemas:
        raise ValueError("Cypher de escritura o inseguro: " + " | ".join(problemas))

    with obtener_driver().session(**_sesion_kwargs()) as sesion:
        resultado: list[dict[str, Any]] = sesion.execute_read(
            lambda tx: [dict(registro) for registro in tx.run(cypher, parametros or {})]
        )
        return resultado


def validar_sintaxis(cypher: str) -> str | None:
    """Compila la consulta con ``EXPLAIN`` sin ejecutarla y devuelve el error si existe."""
    try:
        with obtener_driver().session(**_sesion_kwargs()) as sesion:
            sesion.run("EXPLAIN " + cypher).consume()
        return None
    except Exception as exc:  # Neo4j expone varias subclases según el tipo de fallo.
        return str(exc)
