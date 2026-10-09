"""Elimina todos los datos de la base Neo4j de desarrollo de CIAR.

El script conserva el esquema (índices y restricciones) y borra únicamente nodos
y relaciones. Por seguridad, sin ``--confirmar-eliminacion-total`` solo muestra
el inventario de la base.

Usa primero las credenciales ``NEO4J_INGEST_*``. Si no se han definido, usa el
grupo ``NEO4J_*``; este último debe pertenecer a un usuario con permiso de
escritura. Nunca usa las credenciales ``NEO4J_READ_*``.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Any

from neo4j import WRITE_ACCESS, GraphDatabase

from agente.config.settings import cargar_entorno

CONFIRMACION = "--confirmar-eliminacion-total"
LOTE_POR_DEFECTO = 10_000


@dataclass(frozen=True, slots=True)
class ConexionNeo4j:
    """Parámetros de conexión de escritura, sin exponer la contraseña."""

    uri: str
    usuario: str
    contrasena: str
    database: str


def _texto(clave: str) -> str:
    return os.getenv(clave, "").strip()


def obtener_conexion() -> ConexionNeo4j:
    """Obtiene una configuración de ingesta completa o el grupo base de Neo4j."""

    ingest = {
        "uri": _texto("NEO4J_INGEST_URI"),
        "usuario": _texto("NEO4J_INGEST_USER"),
        "contrasena": _texto("NEO4J_INGEST_PASSWORD"),
        "database": _texto("NEO4J_INGEST_DATABASE"),
    }
    if any(ingest[nombre] for nombre in ("uri", "usuario", "contrasena")):
        faltantes = [nombre for nombre in ("uri", "usuario", "contrasena") if not ingest[nombre]]
        if faltantes:
            raise ValueError(
                "La configuración NEO4J_INGEST_* está incompleta; faltan: "
                + ", ".join(faltantes)
                + "."
            )
        configuracion = ingest
    else:
        configuracion = {
            "uri": _texto("NEO4J_URI"),
            "usuario": _texto("NEO4J_USER"),
            "contrasena": _texto("NEO4J_PASSWORD"),
            "database": _texto("NEO4J_DATABASE"),
        }
        faltantes = [
            nombre
            for nombre in ("uri", "usuario", "contrasena")
            if not configuracion[nombre]
        ]
        if faltantes:
            raise ValueError(
                "No hay credenciales Neo4j de escritura completas. Configure NEO4J_INGEST_* "
                "(recomendado) o NEO4J_URI, NEO4J_USER y NEO4J_PASSWORD. Faltan: "
                + ", ".join(faltantes)
                + "."
            )

    database = configuracion["database"] or "neo4j"
    if database.lower() == "system":
        raise ValueError("La base de sistema no puede limpiarse con este script.")
    return ConexionNeo4j(
        uri=configuracion["uri"],
        usuario=configuracion["usuario"],
        contrasena=configuracion["contrasena"],
        database=database,
    )


def obtener_inventario(session: Any) -> dict[str, Any]:
    """Cuenta nodos, relaciones y su distribución sin modificar la base."""

    resumen = session.run(
        "CALL { MATCH (n) RETURN count(n) AS nodos } "
        "CALL { MATCH ()-[r]->() RETURN count(r) AS relaciones } "
        "RETURN nodos, relaciones"
    ).single()
    por_label = [
        dict(fila)
        for fila in session.run(
            "MATCH (n) "
            "RETURN coalesce(labels(n)[0], '(sin etiqueta)') AS tipo, count(n) AS total "
            "ORDER BY total DESC, tipo"
        )
    ]
    por_relacion = [
        dict(fila)
        for fila in session.run(
            "MATCH ()-[r]->() "
            "RETURN type(r) AS tipo, count(r) AS total ORDER BY total DESC, tipo"
        )
    ]
    return {
        "nodos": int(resumen["nodos"]),
        "relaciones": int(resumen["relaciones"]),
        "por_label": por_label,
        "por_relacion": por_relacion,
    }


def imprimir_inventario(inventario: dict[str, Any]) -> None:
    print(f"Base: {inventario['database']}")
    print(f"Nodos: {inventario['nodos']}")
    print(f"Relaciones: {inventario['relaciones']}")
    if inventario["por_label"]:
        print("Nodos por etiqueta:")
        for fila in inventario["por_label"]:
            print(f"  - {fila['tipo']}: {fila['total']}")
    if inventario["por_relacion"]:
        print("Relaciones por tipo:")
        for fila in inventario["por_relacion"]:
            print(f"  - {fila['tipo']}: {fila['total']}")


def eliminar_por_lotes(session: Any, lote: int) -> int:
    """Borra los nodos junto a sus relaciones en transacciones acotadas."""

    eliminados = 0
    while True:
        resultado = session.execute_write(
            lambda tx: tx.run(
                "CALL { "
                "MATCH (n) WITH n LIMIT $lote "
                "DETACH DELETE n "
                "RETURN count(n) AS eliminados "
                "} "
                "RETURN eliminados",
                lote=lote,
            ).single()
        )
        cantidad = int(resultado["eliminados"])
        eliminados += cantidad
        if cantidad == 0:
            return eliminados
        print(f"Eliminados {eliminados} nodos...", flush=True)


def argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        CONFIRMACION,
        action="store_true",
        help="confirma el borrado de TODOS los nodos y relaciones de la base configurada",
    )
    parser.add_argument(
        "--lote",
        type=int,
        default=LOTE_POR_DEFECTO,
        help=f"número de nodos por transacción (predeterminado: {LOTE_POR_DEFECTO})",
    )
    parsed = parser.parse_args(argv)
    if parsed.lote < 1:
        parser.error("--lote debe ser mayor que cero")
    return parsed


def main(argv: list[str] | None = None) -> int:
    args = argumentos(argv)
    cargar_entorno()
    try:
        conexion = obtener_conexion()
        driver = GraphDatabase.driver(
            conexion.uri,
            auth=(conexion.usuario, conexion.contrasena),
        )
        driver.verify_connectivity()
    except Exception as exc:
        print(f"No se pudo conectar a Neo4j: {exc}", file=sys.stderr)
        return 2

    try:
        with driver.session(
            database=conexion.database,
            default_access_mode=WRITE_ACCESS,
        ) as session:
            inventario = obtener_inventario(session)
            inventario["database"] = conexion.database
            imprimir_inventario(inventario)
            if not args.confirmar_eliminacion_total:
                print(
                    "\nNo se eliminó nada. Para borrar todos esos datos ejecute:\n"
                    "  python scripts/limpiar_datos_neo4j.py --confirmar-eliminacion-total"
                )
                return 0

            print(
                "\nEliminando todos los nodos y relaciones. "
                "Se conservarán índices y restricciones."
            )
            eliminados = eliminar_por_lotes(session, args.lote)
            restante = obtener_inventario(session)
    except Exception as exc:
        print(f"La limpieza no terminó: {exc}", file=sys.stderr)
        return 1
    finally:
        driver.close()

    print(
        f"\nLimpieza terminada: {eliminados} nodos eliminados; "
        f"restan {restante['nodos']} nodos y {restante['relaciones']} relaciones."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
