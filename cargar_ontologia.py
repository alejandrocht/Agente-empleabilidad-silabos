#!/usr/bin/env python3
"""
Carga la ontologia CIAR completa a Neo4j desde los CSV hash de esta carpeta.

Uso:
  python3 cargar_ontologia.py
  python3 cargar_ontologia.py --reset
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import unicodedata
from pathlib import Path
from typing import Iterable

from neo4j import GraphDatabase

BASE_DIR = Path(__file__).resolve().parent
ONTOLOGY_PATH = BASE_DIR / "ontologia.json"
BATCH_SIZE = int(os.getenv("NEO4J_BATCH_SIZE", "5000"))


def load_dotenv() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def normalize_text(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    return "".join(char for char in text if not unicodedata.combining(char)).lower().strip()


def clean_row(row: dict[str, str], nombre_col: str | None = None) -> dict[str, str]:
    cleaned = {key: value.strip() for key, value in row.items() if key and value and value.strip()}
    if nombre_col and cleaned.get(nombre_col):
        cleaned["nombre_norm"] = normalize_text(cleaned[nombre_col])
    return cleaned


def csv_batches(csv_name: str, nombre_col: str | None = None) -> Iterable[list[dict[str, str]]]:
    path = BASE_DIR / csv_name
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        batch: list[dict[str, str]] = []
        for row in reader:
            cleaned = clean_row(row, nombre_col)
            if cleaned:
                batch.append(cleaned)
            if len(batch) >= BATCH_SIZE:
                yield batch
                batch = []
        if batch:
            yield batch


def count_csv_rows(csv_name: str) -> int:
    path = BASE_DIR / csv_name
    with path.open(encoding="utf-8-sig", newline="") as file:
        return max(sum(1 for _ in file) - 1, 0)


def load_join_lookup(csv_name: str, join_pk_col: str, target_pk_col: str) -> dict[str, str]:
    lookup: dict[str, str] = {}
    path = BASE_DIR / csv_name
    with path.open(encoding="utf-8-sig", newline="") as file:
        for row in csv.DictReader(file):
            join_value = (row.get(join_pk_col) or "").strip()
            target_value = (row.get(target_pk_col) or "").strip()
            if join_value and target_value:
                lookup[join_value] = target_value
    return lookup


def relation_batches(source_csv: str, source_col: str, target_col: str) -> Iterable[list[dict[str, str]]]:
    path = BASE_DIR / source_csv
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        batch: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for row in reader:
            source_id = (row.get(source_col) or "").strip()
            target_id = (row.get(target_col) or "").strip()
            key = (source_id, target_id)
            if not source_id or not target_id or key in seen:
                continue
            seen.add(key)
            batch.append({"source_id": source_id, "target_id": target_id})
            if len(batch) >= BATCH_SIZE:
                yield batch
                batch = []
        if batch:
            yield batch


def joined_relation_batches(
    source_csv: str,
    source_col: str,
    join_col: str,
    lookup: dict[str, str],
) -> Iterable[list[dict[str, str]]]:
    path = BASE_DIR / source_csv
    with path.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        batch: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for row in reader:
            source_id = (row.get(source_col) or "").strip()
            target_id = lookup.get((row.get(join_col) or "").strip(), "")
            key = (source_id, target_id)
            if not source_id or not target_id or key in seen:
                continue
            seen.add(key)
            batch.append({"source_id": source_id, "target_id": target_id})
            if len(batch) >= BATCH_SIZE:
                yield batch
                batch = []
        if batch:
            yield batch


def load_entity(session, entity: dict) -> tuple[int, int]:
    label = entity["label"]
    pk = entity["pk"]
    source = entity["fuente"]
    csv_name = source["csv"]
    nombre_col = source.get("nombre_col")

    total = 0
    created = 0
    cypher = (
        f"UNWIND $rows AS row "
        f"MERGE (n:`{label}` {{`{pk}`: row.`{pk}`}}) "
        f"SET n += row"
    )
    for batch in csv_batches(csv_name, nombre_col):
        result = session.run(cypher, rows=batch)
        summary = result.consume()
        total += len(batch)
        created += summary.counters.nodes_created
    return total, created


def load_relation(session, relation: dict, pk_by_label: dict[str, str]) -> tuple[int, int]:
    source_label = relation["source"]
    target_label = relation["target"]
    source_pk = pk_by_label[source_label]
    target_pk = pk_by_label[target_label]
    rel_type = relation["tipo"]
    source = relation["fuente"]

    if "join_csv" in source:
        lookup = load_join_lookup(source["join_csv"], source["join_pk_col"], source["target_pk_col"])
        batches = joined_relation_batches(source["csv"], source["source_pk_col"], source["join_col"], lookup)
    else:
        batches = relation_batches(source["csv"], source["source_pk_col"], source["target_pk_col"])

    total = 0
    created = 0
    cypher = (
        f"UNWIND $rows AS row "
        f"MATCH (source:`{source_label}` {{`{source_pk}`: row.source_id}}) "
        f"MATCH (target:`{target_label}` {{`{target_pk}`: row.target_id}}) "
        f"MERGE (source)-[:`{rel_type}`]->(target)"
    )
    for batch in batches:
        result = session.run(cypher, rows=batch)
        summary = result.consume()
        total += len(batch)
        created += summary.counters.relationships_created
    return total, created


def create_constraints_and_indexes(session, ontology: dict) -> None:
    for entity in ontology["entidades"]:
        label = entity["label"]
        pk = entity["pk"]
        session.run(f"CREATE CONSTRAINT `{label}_{pk}_unique` IF NOT EXISTS FOR (n:`{label}`) REQUIRE n.`{pk}` IS UNIQUE")
        if entity["fuente"].get("nombre_col"):
            session.run(f"CREATE INDEX `{label}_nombre_norm_idx` IF NOT EXISTS FOR (n:`{label}`) ON (n.nombre_norm)")


def print_graph_summary(session) -> None:
    print("\nResumen Neo4j:")
    for record in session.run("MATCH (n) RETURN labels(n)[0] AS label, count(n) AS total ORDER BY label"):
        print(f"  {record['label']:<24} {record['total']:>8} nodos")
    for record in session.run("MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS total ORDER BY type"):
        print(f"  {record['type']:<24} {record['total']:>8} relaciones")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Borra el grafo antes de cargar.")
    args = parser.parse_args()

    load_dotenv()
    uri = os.getenv("NEO4J_URI", "neo4j://127.0.0.1:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")

    ontology = json.loads(ONTOLOGY_PATH.read_text(encoding="utf-8"))
    pk_by_label = {entity["label"]: entity["pk"] for entity in ontology["entidades"]}

    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    print(f"Conectado a {uri}")

    with driver.session() as session:
        if args.reset:
            session.run("MATCH (n) CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS")
            print("Grafo reiniciado.")

        create_constraints_and_indexes(session, ontology)
        print("Constraints e indices listos.")

        print("\nEntidades:")
        for entity in ontology["entidades"]:
            total, created = load_entity(session, entity)
            expected = count_csv_rows(entity["fuente"]["csv"])
            print(f"  OK  {entity['label']:<24} {total:>8}/{expected:<8} filas, {created:>8} nodos nuevos")

        print("\nRelaciones:")
        for relation in ontology["relaciones"]:
            total, created = load_relation(session, relation, pk_by_label)
            pair = f"{relation['source']}->{relation['target']}"
            print(f"  OK  {relation['tipo']:<24} {total:>8} candidatas, {created:>8} nuevas  {pair}")

        print_graph_summary(session)

    driver.close()


if __name__ == "__main__":
    main()
