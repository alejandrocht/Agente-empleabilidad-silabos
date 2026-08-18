"""Pruebas del gate de publicación curricular y de su reversión."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from agente.db.neo4j_importador import ImportadorNeo4j
from agente.normalizador.ejecuciones import GestorEjecuciones
from agente.normalizador.silabos.salida import ARCHIVOS_SALIDA

IDS = {
    "id_competencia": "COMP_0123456789abcdef",
    "id_habilidad": "HAB_0123456789abcdef",
    "id_herramienta": "HERR_0123456789abcdef",
    "id_cob_curricular": "COB_CUR_CAN_0123456789abcdef",
    "id_curso": "CUR_0123456789abcdef",
    "id_silabo": "SIL_0123456789abcdef",
}


class FakeSession:
    def __init__(self, graph: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.graph = graph or {}
        self.modes: list[str] = []

    def __enter__(self) -> FakeSession:
        return self

    def __exit__(self, tipo: Any, valor: Any, traza: Any) -> None:
        return None

    def run(self, cypher: str, parametros: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        parametros = parametros or {}
        if "UNWIND $rows" in cypher:
            return [{"total": len(parametros.get("rows", []))}]
        if "DELETE r" in cypher:
            return [{"total": 3}]
        if "DELETE n" in cypher:
            return [{"total": 2}]
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
        if "MATCH (n:Curso)" in cypher:
            return self.graph.get("cursos", [])
        if "MATCH (n:Silabo)" in cypher:
            return self.graph.get("silabos", [])
        if "MATCH (curso:Curso)-[:TIENE]-(silabo:Silabo)" in cypher:
            return self.graph.get("pares", [])
        return []

    def execute_write(self, funcion: Any) -> Any:
        return funcion(self)


class FakeDriver:
    def __init__(self, graph: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.session_obj = FakeSession(graph)

    def session(self, **kwargs: Any) -> FakeSession:
        self.session_obj.modes.append(kwargs["default_access_mode"])
        return self.session_obj


def _manifest_y_salidas(
    tmp_path: Path,
    filas: dict[str, list[dict[str, str]]],
) -> tuple[GestorEjecuciones, str]:
    gestor = GestorEjecuciones(tmp_path)
    id_ejecucion, directorio = gestor.crear("silabos", "curriculo.zip")
    manifest = directorio / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "id_ejecucion": id_ejecucion,
                "tipo": "silabos",
                "estado": "limpiado",
                "validacion_silabos": {"valida": True},
            }
        ),
        encoding="utf-8",
    )
    gestor._ejecuciones.pop(id_ejecucion)
    salidas = directorio / "salidas"
    salidas.mkdir()
    for archivo, esquema in ARCHIVOS_SALIDA:
        with (salidas / archivo).open("w", encoding="utf-8-sig", newline="") as salida:
            escritor = csv.DictWriter(salida, fieldnames=esquema)
            escritor.writeheader()
            escritor.writerows(filas[archivo])
    return gestor, id_ejecucion


def _filas() -> dict[str, list[dict[str, str]]]:
    return {
        "catalogo_competencias.csv": [
            {
                "id_competencia": IDS["id_competencia"],
                "nombre_competencia": "Pensamiento crítico",
                "descripcion_breve_competencia": "Evalúa evidencia para decidir.",
                "tipo_competencia": "blanda",
            }
        ],
        "catalogo_habilidades.csv": [
            {
                "id_habilidad": IDS["id_habilidad"],
                "nombre_habilidad": "Analizar datos",
                "descripcion_breve": "Interpreta información estructurada.",
            }
        ],
        "catalogo_herramientas.csv": [
            {
                "id_herramienta": IDS["id_herramienta"],
                "nombre_herramienta": "Python",
                "descripcion_breve_herramienta": "Lenguaje para análisis reproducible.",
            }
        ],
        "cobertura_curricular.csv": [
            {
                "id_cob_curricular": IDS["id_cob_curricular"],
                "id_curso": IDS["id_curso"],
                "id_silabo": IDS["id_silabo"],
                "id_competencia": IDS["id_competencia"],
                "id_habilidad": IDS["id_habilidad"],
                "id_herramienta": IDS["id_herramienta"],
            }
        ],
    }


def test_preview_valida_novedad_y_importa_solo_filas_nuevas(tmp_path: Path) -> None:
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, _filas())
    driver = FakeDriver(
        {
            "cursos": [{"id": IDS["id_curso"]}],
            "silabos": [{"id": IDS["id_silabo"]}],
            "pares": [{"id_curso": IDS["id_curso"], "id_silabo": IDS["id_silabo"]}],
        }
    )
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: driver)

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is True
    assert preview["resumen"] == {
        "nuevas_competencias": 1,
        "nuevas_habilidades": 1,
        "nuevas_herramientas": 1,
        "nuevas_coberturas": 1,
        "sin_cambios": 0,
    }
    resultado = importador.importar(id_ejecucion, preview["fingerprint"], confirmar=True)
    assert resultado["estado"] == "completada"
    assert resultado["id_importacion"].startswith("IMP_")

    revertido = importador.revertir(resultado["id_importacion"], confirmar=True)
    assert revertido["estado"] == "revertida"
    assert revertido["reversion"]["nodos_eliminados"] == 2
    assert "WRITE" in driver.session_obj.modes


def test_preview_bloquea_encabezado_fuera_del_contrato(tmp_path: Path) -> None:
    filas = _filas()
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, filas)
    ruta = tmp_path / id_ejecucion / "salidas" / "catalogo_habilidades.csv"
    ruta.write_text("id_habilidad,nombre\n", encoding="utf-8")
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: FakeDriver())

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is False
    assert preview["errores"][0]["codigo"] == "FORMATO_CSV_INVALIDO"


def test_preview_bloquea_nombre_semanticamente_duplicado_en_neo4j(tmp_path: Path) -> None:
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, _filas())
    driver = FakeDriver(
        {
            "competencias": [
                {
                    "id_competencia": "COMP_fedcba9876543210",
                    "nombre_competencia": "Pensamiento  crítico",
                    "descripcion_breve_competencia": "Otra descripción.",
                    "tipo_competencia": "profesional",
                }
            ],
        }
    )
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: driver)

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is False
    assert any(
        conflicto["codigo"] == "NOMBRE_EXISTENTE_CON_OTRO_ID"
        for conflicto in preview["conflictos"]
    )


def test_preview_bloquea_cobertura_sin_padres_curriculares(tmp_path: Path) -> None:
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, _filas())
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: FakeDriver())

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is False
    assert any(
        conflicto["codigo"] == "REFERENCIA_PARENT_NO_EXISTE"
        for conflicto in preview["conflictos"]
    )
