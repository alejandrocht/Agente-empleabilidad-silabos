#!/usr/bin/env python3
"""
Muestra el schema (la ontologia) del grafo CIAR leyendolo EN VIVO desde Neo4j.

En vez de deducir la estructura desde un CSV o desde ontologia.json (forma estatica),
este script usa Neo4jGraph de LangChain para preguntarle a Neo4j su estructura actual
de forma dinamica: que tipos de nodos (labels) hay, que propiedades tienen y como se
conectan entre si.

Requisito: los datos ya deben estar cargados en Neo4j.

Uso:
  python cargar_ontologia.py
"""
from __future__ import annotations

import os
from pathlib import Path

from langchain_neo4j import Neo4jGraph

# Carpeta donde vive este archivo (para encontrar el .env al lado).
BASE_DIR = Path(__file__).resolve().parent


def cargar_variables_entorno() -> None:
    """Lee el archivo .env (si existe) y copia sus valores a las variables de entorno."""
    ruta_env = BASE_DIR / ".env"
    if not ruta_env.exists():
        return

    for linea_cruda in ruta_env.read_text(encoding="utf-8").splitlines():
        linea = linea_cruda.strip()
        # Saltamos lineas vacias, comentarios (#) y las que no tengan un "=".
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        # setdefault NO pisa una variable que ya este definida en el entorno.
        os.environ.setdefault(clave.strip(), valor.strip().strip('"').strip("'"))


def conectar_neo4j() -> Neo4jGraph:
    """Crea la conexion a Neo4j usando Neo4jGraph con los datos del .env."""
    uri = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
    usuario = os.getenv("NEO4J_USER", "neo4j")
    contrasena = os.getenv("NEO4J_PASSWORD", "")

    # Al crearse, Neo4jGraph se conecta y descubre el schema automaticamente.
    grafo = Neo4jGraph(
        url=uri,
        username=usuario,
        password=contrasena,
    )
    return grafo


def mostrar_schema(grafo: Neo4jGraph) -> None:
    """Refresca y muestra el schema que Neo4j tiene en este momento."""
    # refresh_schema vuelve a preguntarle a Neo4j su estructura actual (en vivo).
    grafo.refresh_schema()

    print("=" * 60)
    print("SCHEMA DEL GRAFO CIAR (leido en vivo desde Neo4j)")
    print("=" * 60)
    # grafo.schema es un texto ya formateado con nodos, propiedades y relaciones.
    print(grafo.schema)


def mostrar_conteos(grafo: Neo4jGraph) -> None:
    """Muestra cuantos nodos hay por cada tipo (label) y cuantas relaciones por tipo."""
    # grafo.query ejecuta Cypher y devuelve una lista de diccionarios.
    print("\nNodos por label:")
    filas_nodos = grafo.query(
        "MATCH (n) RETURN labels(n)[0] AS label, count(n) AS total ORDER BY total DESC"
    )
    for fila in filas_nodos:
        if fila["label"]:
            print(f"  {fila['label']:<24} {fila['total']:>8} nodos")

    print("\nRelaciones por tipo:")
    filas_rels = grafo.query(
        "MATCH ()-[r]->() RETURN type(r) AS tipo, count(r) AS total ORDER BY total DESC"
    )
    for fila in filas_rels:
        print(f"  {fila['tipo']:<24} {fila['total']:>8} relaciones")


def main() -> None:
    cargar_variables_entorno()

    grafo = conectar_neo4j()
    print(f"Conectado a {os.getenv('NEO4J_URI', 'neo4j://127.0.0.1:7687')}")

    mostrar_schema(grafo)
    mostrar_conteos(grafo)


if __name__ == "__main__":
    main()
