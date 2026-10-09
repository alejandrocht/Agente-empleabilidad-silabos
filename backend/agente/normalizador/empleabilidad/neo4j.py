"""Publicación idempotente de resultados laborales hacia Neo4j.

Este módulo no forma parte del agente conversacional de solo lectura. Se usa
únicamente desde los endpoints explícitos de publicación del normalizador.
"""

from __future__ import annotations

import csv
import hashlib
from typing import Any

from neo4j import WRITE_ACCESS, GraphDatabase

from agente.config.settings import texto
from agente.normalizador.ejecuciones import GestorEjecuciones, gestor_ejecuciones


class ImportacionEmpleabilidadError(RuntimeError):
    """Error seguro para el contrato HTTP de publicación laboral."""

    def __init__(self, mensaje: str, status_code: int = 400) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status_code = status_code


ARCHIVOS = (
    "empresa.csv",
    "oferta_laboral.csv",
    "puesto.csv",
    "catalogo_empleabilidad.csv",
    "habilidades_empleabilidad.csv",
    "herramientas_empleabilidad.csv",
    "requerimiento_laboral.csv",
)


class ImportadorEmpleabilidadNeo4j:
    """Previsualiza y escribe solamente publicaciones aún inexistentes."""

    def __init__(self, gestor: GestorEjecuciones = gestor_ejecuciones) -> None:
        self.gestor = gestor

    def previsualizar(self, id_ejecucion: str) -> dict[str, object]:
        filas, fingerprint = self._cargar(id_ejecucion)
        existentes = self._ofertas_existentes(
            [fila["id_ofe_laboral"] for fila in filas["oferta_laboral.csv"]]
        )
        nuevas = [
            fila
            for fila in filas["oferta_laboral.csv"]
            if fila["id_ofe_laboral"] not in existentes
        ]
        return {
            "id_ejecucion": id_ejecucion,
            "fingerprint": fingerprint,
            "puede_importar": True,
            "mensaje": "La consulta de duplicados se ejecutó correctamente.",
            "resumen": {
                "publicaciones_nuevas": len(nuevas),
                "publicaciones_existentes": len(existentes),
                "consultas_ejecutadas": 1,
            },
            "ofertas": {
                "nuevas": [fila["id_ofe_laboral"] for fila in nuevas],
                "existentes": sorted(existentes),
            },
        }

    def importar(self, id_ejecucion: str, fingerprint: str, confirmar: bool) -> dict[str, object]:
        if not confirmar:
            raise ImportacionEmpleabilidadError("La publicación requiere confirmación explícita.")
        filas, fingerprint_actual = self._cargar(id_ejecucion)
        if fingerprint != fingerprint_actual:
            raise ImportacionEmpleabilidadError(
                "Las salidas cambiaron desde la previsualización. Vuelve a revisar la carga.",
                409,
            )
        existentes = self._ofertas_existentes(
            [fila["id_ofe_laboral"] for fila in filas["oferta_laboral.csv"]]
        )
        ofertas_nuevas = [
            fila for fila in filas["oferta_laboral.csv"] if fila["id_ofe_laboral"] not in existentes
        ]
        ids_nuevos = {fila["id_ofe_laboral"] for fila in ofertas_nuevas}
        if ofertas_nuevas:
            self._escribir(filas, ofertas_nuevas, ids_nuevos)
        return {
            "id_ejecucion": id_ejecucion,
            "mensaje": "La consulta fue ejecutada; solo se insertaron publicaciones nuevas.",
            "resumen": {
                "publicaciones_creadas": len(ofertas_nuevas),
                "publicaciones_omitidas": len(existentes),
                "consultas_ejecutadas": 1,
            },
        }

    def _cargar(self, id_ejecucion: str) -> tuple[dict[str, list[dict[str, str]]], str]:
        try:
            estado = self.gestor.obtener(id_ejecucion)
        except KeyError as exc:
            raise ImportacionEmpleabilidadError("La ejecución no existe.", 404) from exc
        if estado.get("tipo") != "empleabilidad" or estado.get("estado") not in {
            "normalizado",
            "normalizado_con_advertencias",
        }:
            raise ImportacionEmpleabilidadError(
                "La ejecución laboral no tiene salidas publicables.", 409
            )
        raiz = self.gestor.base_dir / id_ejecucion / "salidas"
        filas: dict[str, list[dict[str, str]]] = {}
        digest = hashlib.sha256()
        for nombre in ARCHIVOS:
            ruta = raiz / nombre
            if not ruta.is_file():
                raise ImportacionEmpleabilidadError(
                    f"La ejecución no contiene {nombre}.", 409
                )
            contenido = ruta.read_bytes()
            digest.update(nombre.encode("utf-8"))
            digest.update(b"\0")
            digest.update(contenido)
            with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
                filas[nombre] = [
                    {clave: str(valor or "").strip() for clave, valor in fila.items()}
                    for fila in csv.DictReader(archivo)
                ]
        # El pipeline oficial usa ``id_ofe_laboral``; el contrato histórico
        # del normalizador usaba ``id_oferta_laboral``. Se acepta ambos para
        # publicar sobre el mismo modelo de Neo4j sin duplicar relaciones.
        for fila in filas["requerimiento_laboral.csv"]:
            fila["id_oferta_laboral"] = (
                fila.get("id_oferta_laboral") or fila.get("id_ofe_laboral") or ""
            )
        return filas, digest.hexdigest()

    def _sesion(self) -> Any:
        uri = texto("NEO4J_INGEST_URI") or texto("NEO4J_URI")
        usuario = texto("NEO4J_INGEST_USER") or texto("NEO4J_USER")
        contrasena = texto("NEO4J_INGEST_PASSWORD") or texto("NEO4J_PASSWORD")
        base = texto("NEO4J_INGEST_DATABASE") or texto("NEO4J_DATABASE", "neo4j")
        if not uri or not usuario or not contrasena:
            raise ImportacionEmpleabilidadError(
                "Faltan credenciales de ingestión Neo4j para publicar empleabilidad.", 503
            )
        driver = GraphDatabase.driver(uri, auth=(usuario, contrasena))
        driver.verify_connectivity()
        return driver, driver.session(database=base, default_access_mode=WRITE_ACCESS)

    def _ofertas_existentes(self, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        driver, sesion = self._sesion()
        try:
            resultado = sesion.run(
                "UNWIND $ids AS id OPTIONAL MATCH (o:Oferta_Laboral {id_ofe_laboral: id}) "
                "RETURN id, count(o) > 0 AS existe",
                ids=ids,
            )
            return {str(fila["id"]) for fila in resultado if fila["existe"]}
        finally:
            sesion.close()
            driver.close()

    def _escribir(
        self,
        filas: dict[str, list[dict[str, str]]],
        ofertas_nuevas: list[dict[str, str]],
        ids_nuevos: set[str],
    ) -> None:
        driver, sesion = self._sesion()
        try:
            empresas_ids = {fila.get("id_empresa") for fila in ofertas_nuevas}
            empresas = [
                fila for fila in filas["empresa.csv"] if fila.get("id_empresa") in empresas_ids
            ]
            puestos = [
                fila for fila in filas["puesto.csv"] if fila.get("id_ofe_laboral") in ids_nuevos
            ]
            requerimientos = [
                fila
                for fila in filas["requerimiento_laboral.csv"]
                if fila.get("id_oferta_laboral") in ids_nuevos
            ]
            for etiqueta, campo, nombre in (
                ("Competencia", "id_competencia", "catalogo_empleabilidad.csv"),
                ("Habilidad", "id_habilidad", "habilidades_empleabilidad.csv"),
                ("Herramienta", "id_herramienta", "herramientas_empleabilidad.csv"),
            ):
                sesion.run(
                    f"UNWIND $rows AS row MERGE (n:{etiqueta} {{{campo}: row.{campo}}}) "
                    "ON CREATE SET n += row",
                    rows=filas[nombre],
                ).consume()
            sesion.run(
                "UNWIND $rows AS row MERGE (e:Empresa {id_empresa: row.id_empresa}) "
                "ON CREATE SET e += row",
                rows=empresas,
            ).consume()
            sesion.run(
                "UNWIND $rows AS row MERGE (p:Puesto {id_puesto: row.id_puesto}) "
                "ON CREATE SET p += row",
                rows=puestos,
            ).consume()
            sesion.run(
                "UNWIND $rows AS row MERGE (o:Oferta_Laboral {id_ofe_laboral: row.id_ofe_laboral}) "
                "ON CREATE SET o += row WITH o, row "
                "MATCH (e:Empresa {id_empresa: row.id_empresa}) "
                "MATCH (p:Puesto {id_puesto: row.id_puesto}) "
                "MERGE (e)-[:PUBLICA]->(o) MERGE (o)-[:OFRECE]->(p)",
                rows=[
                    {
                        **oferta,
                        "id_puesto": next(
                            (
                                puesto["id_puesto"]
                                for puesto in puestos
                                if puesto["id_ofe_laboral"] == oferta["id_ofe_laboral"]
                            ),
                            "",
                        ),
                    }
                    for oferta in ofertas_nuevas
                ],
            ).consume()
            if any(fila.get("id_competencia") for fila in requerimientos):
                sesion.run(
                    "UNWIND $rows AS row "
                    "MERGE (r:Requerimiento_Laboral {id_req_laboral: row.id_req_laboral}) "
                    "ON CREATE SET r += row WITH r, row "
                    "MATCH (o:Oferta_Laboral {id_ofe_laboral: row.id_oferta_laboral}) "
                    "MATCH (p:Puesto {id_puesto: row.id_puesto}) "
                    "MATCH (e:Empresa {id_empresa: row.id_empresa}) "
                    "MATCH (c:Competencia {id_competencia: row.id_competencia}) "
                    "MATCH (h:Habilidad {id_habilidad: row.id_habilidad}) "
                    "MERGE (o)-[:TIENE]->(r) MERGE (p)-[:DEFIINE]->(r) "
                    "MERGE (e)-[:PIDE]->(r) MERGE (r)-[:REQUIERE]->(c) MERGE (r)-[:REQUIERE]->(h)",
                    rows=requerimientos,
                ).consume()
            else:
                sesion.run(
                    "UNWIND $rows AS row "
                    "MERGE (r:Requerimiento_Laboral {id_req_laboral: row.id_req_laboral}) "
                    "ON CREATE SET r += row WITH r, row "
                    "MATCH (o:Oferta_Laboral {id_ofe_laboral: row.id_oferta_laboral}) "
                    "MATCH (p:Puesto {id_puesto: row.id_puesto}) "
                    "MATCH (e:Empresa {id_empresa: row.id_empresa}) "
                    "MATCH (h:Habilidad {id_habilidad: row.id_habilidad}) "
                    "MERGE (o)-[:TIENE]->(r) MERGE (p)-[:DEFIINE]->(r) "
                    "MERGE (e)-[:PIDE]->(r) MERGE (r)-[:REQUIERE]->(h)",
                    rows=requerimientos,
                ).consume()
        finally:
            sesion.close()
            driver.close()


importador_empleabilidad_neo4j = ImportadorEmpleabilidadNeo4j()
