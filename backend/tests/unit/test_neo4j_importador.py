"""Pruebas del gate de publicación curricular y de su reversión."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from agente.db.neo4j_importador import ImportadorNeo4j
from agente.normalizador.ejecuciones import GestorEjecuciones
from agente.normalizador.silabos import salida_catalogos


def test_importer_defers_legacy_output_loader() -> None:
    probe = """
import sys
from agente.db import neo4j_importador

assert "agente.normalizador.silabos.salida" not in sys.modules
assert callable(neo4j_importador._cargar_salida_legacy)
"""
    entorno = os.environ.copy()
    backend = str(Path(__file__).resolve().parents[2])
    entorno["PYTHONPATH"] = os.pathsep.join(
        parte for parte in (backend, entorno.get("PYTHONPATH")) if parte
    )
    subprocess.run(
        [sys.executable, "-c", probe],
        cwd=backend,
        env=entorno,
        check=True,
        capture_output=True,
        text=True,
    )


IDS = {
    "id_competencia": "COMP_0123456789abcdef",
    "id_habilidad": "HAB_0123456789abcdef",
    "id_herramienta": "HERR_0123456789abcdef",
    "id_cob_curricular": "COB_CUR_0123456789abcdef",
    "id_curso": "CUR_0123456789abcdef",
    "id_silabo": "SIL_0123456789abcdef",
    "id_carrera": "CAR_01375f53651cff38",
}


class FakeSession:
    def __init__(self, graph: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.graph = graph or {}
        self.modes: list[str] = []
        self.queries: list[str] = []

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, tipo: Any, valor: Any, traza: Any) -> None:
        return None

    def run(self, cypher: str, parametros: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        parametros = parametros or {}
        self.queries.append(cypher)
        if "UNWIND $rows" in cypher:
            return [{"total": len(parametros.get("rows", []))}]
        if "DELETE r" in cypher:
            return [{"total": 3}]
        if "DELETE n" in cypher:
            return [{"total": 2}]
        if "CiarImportacionCursoReversion" in cypher and "curso.coordinador = CASE" in cypher:
            return self.graph.get("restauraciones", [{"total": 0}])
        if "SET n._ciar_import_id = NULL" in cypher:
            return [{"total": 0}]
        if "MATCH (n:Competencia)" in cypher:
            return self.graph.get("competencias", [])
        if "MATCH (n:Habilidad)" in cypher:
            return self.graph.get("habilidades", [])
        if "MATCH (n:Herramienta)" in cypher:
            return self.graph.get("herramientas", [])
        if "MATCH (n:Cobertura_Curricular)" in cypher:
            return self.graph.get("coberturas", [])
        if "RETURN n.id_curso AS id_curso" in cypher:
            return self.graph.get("cursos_detalle", [])
        if "MATCH (n:Curso)" in cypher:
            return self.graph.get("cursos", [])
        if "MATCH (n:Carrera)" in cypher:
            return self.graph.get("carreras", [])
        if "MATCH (n:Silabo)" in cypher:
            return self.graph.get("silabos", [])
        if "MATCH (curso:Curso)-[:TIENE]->(silabo:Silabo)" in cypher:
            return self.graph.get("pares", [])
        if "MATCH (carrera:Carrera)-[:ENSENIA]->(curso:Curso)" in cypher:
            return self.graph.get("pares_carrera_curso", [])
        return []

    def execute_write(self, funcion: Any) -> Any:
        return funcion(self)


class FakeDriver:
    def __init__(self, graph: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.session_obj = FakeSession(graph)

    def session(self, **kwargs: Any) -> FakeSession:
        self.session_obj.modes.append(kwargs["default_access_mode"])
        return self.session_obj


def _manifest_tecnico(
    tmp_path: Path,
    *,
    decision: str = "ALLOW_IMPORT",
) -> tuple[GestorEjecuciones, str]:
    gestor = GestorEjecuciones(tmp_path)
    id_ejecucion, directorio = gestor.crear("silabos", "curriculo.zip")
    (directorio / "manifest.json").write_text(
        json.dumps(
            {
                "id_ejecucion": id_ejecucion,
                "tipo": "silabos",
                "estado": "limpiado",
                "validacion_silabos": {"valida": True},
                "configuracion_curricular": {"modo_analista": "technical"},
                "release_gate": {
                    "version": "curricular-release-gate/v1",
                    "decision": decision,
                    "blockers": [] if decision == "ALLOW_IMPORT" else ["BLOCKED"],
                },
            }
        ),
        encoding="utf-8",
    )
    gestor._ejecuciones.pop(id_ejecucion)
    salida_catalogos.construir_catalogos_curriculares(
        [
            {
                "id_curso": IDS["id_curso"],
                "id_silabo": IDS["id_silabo"],
                "carrera": "SISTEMAS",
                "periodo": "2026-2",
                "datos": {
                    "nombre_curso": "Estructura de datos",
                    "codigo_curso": "SIS501",
                    "competencias_declaradas": [
                        {
                            "nombre": "Pensamiento crítico",
                            "descripcion": "Evalúa evidencia para decidir.",
                            "codigo": "G1",
                            "tipo": "generica",
                        }
                    ],
                    "logro_general": "Diseña soluciones mantenibles.",
                    "programa_analitico_detalle": [
                        {"semana": "1", "tema": "Fundamentos", "contenido": "Tipos."}
                    ],
                },
            }
        ],
        directorio / "salidas",
        carrera="SISTEMAS",
        periodo_academico="2026-2",
    )
    return gestor, id_ejecucion


def test_modo_tecnico_importa_grafo_canonico_y_revierte_sus_creaciones(
    tmp_path: Path,
) -> None:
    gestor, id_ejecucion = _manifest_tecnico(tmp_path)
    driver = FakeDriver()
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: driver)

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is True
    assert {archivo["archivo"] for archivo in preview["archivos"]} == {
        "curso.csv",
        "silabo.csv",
        "catalogo_competencias.csv",
        "catalogo_logros.csv",
        "cobertura_curricular.csv",
    }
    resultado = importador.importar(id_ejecucion, preview["fingerprint"], confirmar=True)
    assert resultado["estado"] == "completada"
    consultas = driver.session_obj.queries
    assert not any("ContenidoSemanal" in consulta for consulta in consultas)
    assert any("_ciar_import_created = true" in consulta for consulta in consultas)
    assert not any("Habilidad" in consulta or "Herramienta" in consulta for consulta in consultas)

    revertido = importador.revertir(resultado["id_importacion"], confirmar=True)
    assert revertido["estado"] == "revertida"
    assert any("_ciar_import_created = true" in consulta for consulta in consultas)


def test_modo_tecnico_bloqueado_no_lee_neo4j(
    tmp_path: Path,
) -> None:
    gestor, id_ejecucion = _manifest_tecnico(tmp_path, decision="BLOCK_IMPORT")
    driver = FakeDriver()
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: driver)

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is False
    assert preview["errores"][0]["codigo"] == "RELEASE_GATE_BLOQUEADO"
    assert driver.session_obj.modes == []
    assert driver.session_obj.queries == []
