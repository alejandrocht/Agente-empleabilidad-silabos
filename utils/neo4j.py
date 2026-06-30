"""
Todo lo relacionado con Neo4j en un solo lugar:
  - conexion (driver) cacheada
  - introspeccion del schema EN VIVO (que nodos/relaciones/props hay)
  - construccion del schema en texto (para darselo al LLM)
  - ejecucion de consultas de SOLO LECTURA

Esta logica viene del antiguo agente_consola.py, reorganizada y comentada.
"""
from __future__ import annotations

import os
# lru_cache guarda en memoria el resultado de una funcion para no recalcularlo cada vez.
from functools import lru_cache

# GraphDatabase es el driver oficial de Neo4j para Python.
from neo4j import GraphDatabase


@lru_cache(maxsize=1)
def obtener_driver():
    """Crea (una sola vez) la conexion a Neo4j usando los datos del .env."""
    # Direccion de la base. Por defecto, Neo4j local.
    uri = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
    # Usuario y contrasena de Neo4j.
    usuario = os.getenv("NEO4J_USER", "neo4j")
    contrasena = os.getenv("NEO4J_PASSWORD", "")

    # Creamos el driver (el "telefono" para hablar con Neo4j).
    driver = GraphDatabase.driver(uri, auth=(usuario, contrasena))
    # verify_connectivity falla rapido y claro si Neo4j esta apagado o mal configurado.
    driver.verify_connectivity()
    return driver


@lru_cache(maxsize=1)
def introspeccionar_schema() -> dict:
    """Descubre la ontologia EN VIVO desde Neo4j. Se cachea: solo corre una vez por sesion."""
    # Abrimos una sesion (una "conversacion") con Neo4j.
    with obtener_driver().session() as sesion:
        # 1) Labels (tipos de nodo) con su conteo, del mas comun al menos comun.
        conteo_por_label: dict[str, int] = {
            registro["label"]: registro["total"]
            for registro in sesion.run(
                "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS total ORDER BY total DESC"
            )
            if registro["label"]  # ignoramos nodos sin label
        }
        labels = list(conteo_por_label.keys())

        # Si no hay labels, la base esta vacia: avisamos con un mensaje util.
        if not labels:
            raise RuntimeError(
                "Neo4j esta vacio: no hay labels. Carga los datos antes de iniciar el agente."
            )

        # 2) Propiedades de cada label (que campos guarda cada tipo de nodo).
        props_por_label: dict[str, list[str]] = {}
        for registro in sesion.run(
            "CALL db.schema.nodeTypeProperties() YIELD nodeLabels, propertyName "
            "RETURN nodeLabels[0] AS label, collect(DISTINCT propertyName) AS props"
        ):
            if registro["label"]:
                props_por_label[registro["label"]] = sorted(registro["props"])

        # 3) Topologia: que nodos se conectan con que relaciones (sin direccion).
        topologia: list[dict] = []
        for registro in sesion.run(
            "CALL db.schema.visualization() YIELD relationships "
            "UNWIND relationships AS rel "
            "RETURN labels(startNode(rel))[0] AS src, type(rel) AS tipo_rel, "
            "       labels(endNode(rel))[0] AS tgt"
        ):
            topologia.append(
                {"src": registro["src"], "rel": registro["tipo_rel"], "tgt": registro["tgt"]}
            )

        # 3b) Frecuencia de cada tipo de relacion (cuantas veces aparece en el grafo).
        frecuencia_rel: dict[str, int] = {
            registro["rel"]: registro["freq"]
            for registro in sesion.run(
                "MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS freq"
            )
        }
        # Pegamos la frecuencia a cada relacion de la topologia y ordenamos por densidad.
        for t in topologia:
            t["freq"] = frecuencia_rel.get(t["rel"], 0)
        topologia.sort(key=lambda x: x["freq"], reverse=True)

        # 4) Detectamos cual es la propiedad "nombre" de cada label.
        #    Cada label puede usar "nombre", "nombre_carrera", "nombre_curso", etc.
        #    (excepto "nombre_norm", que es el nombre normalizado interno).
        prop_nombre_por_label: dict[str, str] = {}
        for label, props in props_por_label.items():
            for p in props:
                if p == "nombre":
                    prop_nombre_por_label[label] = p
                    break
                if p.startswith("nombre_") and p != "nombre_norm":
                    prop_nombre_por_label.setdefault(label, p)

        # 4b) Sacamos hasta 5 nombres reales de ejemplo por label.
        #     Esto ayuda al LLM a ver datos reales y no inventarse nombres.
        ejemplos: dict[str, list[str]] = {}
        for label, prop_nombre in prop_nombre_por_label.items():
            filas = sesion.run(
                f"MATCH (n:`{label}`) WHERE n.`{prop_nombre}` IS NOT NULL "
                f"RETURN n.`{prop_nombre}` AS muestra LIMIT 5"
            )
            valores = [f["muestra"] for f in filas if f["muestra"]]
            if valores:
                ejemplos[label] = valores

    # Devolvemos todo lo descubierto en un diccionario.
    return {
        "labels": conteo_por_label,
        "props": props_por_label,
        "topology": topologia,
        "samples": ejemplos,
    }


def construir_schema_texto() -> str:
    """Convierte el schema descubierto en un TEXTO legible para meterlo en el prompt del LLM."""
    intro = introspeccionar_schema()

    # Iremos juntando lineas de texto en esta lista.
    lineas = [
        "ONTOLOGIA CIAR EN NEO4J (descubierta en vivo)",
        "Usa exactamente estos labels, relaciones y propiedades.",
        "",
        "NODOS (label, conteo, propiedades)",
    ]

    # Una linea por cada label con su conteo y sus propiedades.
    for label, total in intro["labels"].items():
        props = intro["props"].get(label, [])
        props_str = ", ".join(props) if props else "(sin propiedades indexadas)"
        lineas.append(f"- :{label} ({total} nodos) props: {props_str}")

    # Bloque de relaciones (sin direccion, para evitar errores de flecha invertida).
    lineas.append("")
    lineas.append("RELACIONES (sin direccion para evitar errores, ordenadas por densidad)")
    for t in intro["topology"]:
        lineas.append(f"- (:{t['src']})-[:{t['rel']}]-(:{t['tgt']})  [freq: {t.get('freq', 0)}]")

    # Bloque de ejemplos de nombres reales (si los hay).
    if intro["samples"]:
        lineas.append("")
        lineas.append("EJEMPLOS DE DATOS REALES (usa estos nombres antes de inventar)")
        for label, nombres in intro["samples"].items():
            lineas.append(f"- {label}: {', '.join(nombres)}")

    # Unimos todas las lineas con saltos de linea.
    return "\n".join(lineas)


def ejecutar_lectura(cypher: str) -> list[dict]:
    """Ejecuta una consulta Cypher de SOLO LECTURA y devuelve las filas como diccionarios."""
    with obtener_driver().session() as sesion:
        # execute_read garantiza que la transaccion es de lectura.
        return sesion.execute_read(
            lambda tx: [dict(registro) for registro in tx.run(cypher)]
        )


def validar_sintaxis(cypher: str) -> str | None:
    """Valida un Cypher SIN ejecutarlo, usando EXPLAIN.

    EXPLAIN hace que Neo4j compile y planifique la consulta (revisa sintaxis y esquema)
    pero NO la ejecuta ni toca datos. Devuelve None si esta bien, o el mensaje de error.
    """
    try:
        with obtener_driver().session() as sesion:
            # Anteponemos EXPLAIN: Neo4j solo compila. consume() fuerza esa compilacion.
            sesion.run("EXPLAIN " + cypher).consume()
        # Si no lanzo excepcion, la consulta es valida sintacticamente.
        return None
    except Exception as exc:
        # Si Neo4j se quejo (ej. WHERE mal puesto), devolvemos su mensaje de error.
        return str(exc)
