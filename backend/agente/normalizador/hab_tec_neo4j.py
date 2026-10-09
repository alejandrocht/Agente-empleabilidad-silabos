"""Publicación idempotente del catálogo HAB_TEC hacia Neo4j.

Los embeddings continúan siendo un índice local. Neo4j almacena únicamente el
catálogo estructurado: un nodo :Habilidad por ID y el contexto de cada carrera
en la relación que los asocia.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Iterable
from typing import Any, Protocol

from neo4j import WRITE_ACCESS, GraphDatabase

from agente.config.settings import texto


def normalize(value: object) -> str:
    """Normaliza nombres de carrera sin depender del módulo legado eliminado."""

    texto = unicodedata.normalize("NFKD", str(value or ""))
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return " ".join(texto.casefold().split())


class ErrorPublicacionHabTec(RuntimeError):
    """Fallo controlado durante la publicación del catálogo estructurado."""


class ResultadoCypher(Protocol):
    def consume(self) -> Any: ...


class SesionNeo4j(Protocol):
    def run(self, cypher: str, **parametros: Any) -> Iterable[Any]: ...

    def close(self) -> None: ...


Publicador = Callable[[Iterable[Any], str], dict[str, int]]


class PublicadorHabTecNeo4j:
    """Crea o actualiza habilidades técnicas sin guardar embeddings en Neo4j."""

    def publicar(self, registros: Iterable[Any], id_catalogo: str) -> dict[str, int]:
        filas_catalogo = list(registros)
        if not filas_catalogo:
            raise ErrorPublicacionHabTec(
                "El catálogo HAB_TEC no contiene habilidades para publicar."
            )

        driver, sesion = self._sesion()
        try:
            carreras = self._carreras_por_nombre(sesion)
            filas = self._resolver_asociaciones(filas_catalogo, carreras, id_catalogo)
            resultado = sesion.run(
                "UNWIND $filas AS fila "
                "MERGE (habilidad:Habilidad {id_habilidad: fila.id_habilidad}) "
                "ON CREATE SET habilidad.creado_por = 'catalogo_hab_tec' "
                "SET habilidad.nombre_habilidad = fila.nombre_habilidad, "
                "habilidad.tipo_habilidad = 'tecnica', "
                "habilidad.origen_catalogo = 'catalogo_hab_tec', "
                "habilidad.ultimo_catalogo_hab_tec = fila.id_catalogo "
                "WITH habilidad, fila "
                "MATCH (carrera:Carrera {id_carrera: fila.id_carrera}) "
                "MERGE (carrera)-[rel:TIENE_HABILIDAD_TECNICA]->(habilidad) "
                "SET rel.nombre_contextual = fila.nombre_contextual, "
                "rel.descripcion_contextual = fila.descripcion_contextual, "
                "rel.origen_catalogo = 'catalogo_hab_tec', "
                "rel.ultimo_catalogo_hab_tec = fila.id_catalogo "
                "RETURN count(DISTINCT habilidad) AS habilidades, count(rel) AS asociaciones",
                filas=filas,
            )
            fila_resultado = next(iter(resultado), None)
            if fila_resultado is None:
                raise ErrorPublicacionHabTec(
                    "Neo4j no confirmó la publicación del catálogo HAB_TEC."
                )
            return {
                "habilidades": int(fila_resultado["habilidades"]),
                "asociaciones": int(fila_resultado["asociaciones"]),
            }
        finally:
            sesion.close()
            driver.close()

    @staticmethod
    def _carreras_por_nombre(sesion: SesionNeo4j) -> dict[str, list[str]]:
        carreras: dict[str, list[str]] = {}
        for fila in sesion.run(
            "MATCH (carrera:Carrera) "
            "RETURN carrera.id_carrera AS id_carrera, "
            "coalesce(carrera.nombre_carrera, carrera.nombre) AS nombre_carrera"
        ):
            id_carrera = str(fila["id_carrera"] or "").strip()
            nombre = normalize(fila["nombre_carrera"])
            if id_carrera and nombre:
                carreras.setdefault(nombre, []).append(id_carrera)
        return carreras

    @staticmethod
    def _resolver_asociaciones(
        registros: list[Any],
        carreras: dict[str, list[str]],
        id_catalogo: str,
    ) -> list[dict[str, str]]:
        nombres_canonicos: dict[str, str] = {}
        for registro in sorted(registros, key=lambda item: int(item.fila)):
            id_habilidad = str(registro.id_hab_tec).strip()
            nombres_canonicos.setdefault(id_habilidad, str(registro.nombre).strip())
        faltantes: set[str] = set()
        ambiguas: set[str] = set()
        filas: list[dict[str, str]] = []
        for registro in registros:
            id_habilidad = str(registro.id_hab_tec).strip()
            nombre_carrera = str(registro.carrera).strip()
            opciones = carreras.get(normalize(nombre_carrera), [])
            if not opciones:
                faltantes.add(nombre_carrera)
                continue
            if len(opciones) != 1:
                ambiguas.add(nombre_carrera)
                continue
            filas.append(
                {
                    "id_habilidad": id_habilidad,
                    "nombre_habilidad": nombres_canonicos[id_habilidad],
                    "id_carrera": opciones[0],
                    "nombre_contextual": str(registro.nombre).strip(),
                    "descripcion_contextual": str(registro.descripcion).strip(),
                    "id_catalogo": id_catalogo,
                }
            )
        problemas: list[str] = []
        if faltantes:
            problemas.append("sin Carrera en Neo4j: " + ", ".join(sorted(faltantes)))
        if ambiguas:
            problemas.append("con Carrera ambigua en Neo4j: " + ", ".join(sorted(ambiguas)))
        if problemas:
            raise ErrorPublicacionHabTec(
                "No se publicó el catálogo HAB_TEC; hay carreras " + "; ".join(problemas) + "."
            )
        return filas

    @staticmethod
    def _sesion() -> tuple[Any, Any]:
        uri = texto("NEO4J_INGEST_URI") or texto("NEO4J_URI")
        usuario = texto("NEO4J_INGEST_USER") or texto("NEO4J_USER")
        contrasena = texto("NEO4J_INGEST_PASSWORD") or texto("NEO4J_PASSWORD")
        base = texto("NEO4J_INGEST_DATABASE") or texto("NEO4J_DATABASE", "neo4j")
        if not uri or not usuario or not contrasena:
            raise ErrorPublicacionHabTec(
                "Faltan credenciales de ingestión Neo4j para publicar el catálogo HAB_TEC."
            )
        driver = GraphDatabase.driver(uri, auth=(usuario, contrasena))
        driver.verify_connectivity()
        return driver, driver.session(database=base, default_access_mode=WRITE_ACCESS)


publicador_hab_tec_neo4j = PublicadorHabTecNeo4j()
