"""Pruebas del gate de publicación curricular y de su reversión."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from agente.db.neo4j_importador import ImportadorNeo4j
from agente.normalizador.ejecuciones import GestorEjecuciones
from agente.normalizador.silabos.salida import ARCHIVOS_SALIDA

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


def _manifest_y_salidas(
    tmp_path: Path,
    filas: dict[str, list[dict[str, str]]],
    silabos: list[dict[str, Any]] | None = None,
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
                "release_gate": {
                    "version": "curricular-release-gate/v1",
                    "decision": "ALLOW_IMPORT",
                    "blockers": [],
                },
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
    limpios = directorio / "limpios"
    limpios.mkdir()
    registros_silabo = silabos if silabos is not None else _silabos()
    (limpios / "silabos.jsonl").write_text(
        "".join(json.dumps(registro, ensure_ascii=False) + "\n" for registro in registros_silabo),
        encoding="utf-8",
    )
    return gestor, id_ejecucion


def _filas() -> dict[str, list[dict[str, str]]]:
    return {
        "curso.csv": [
            {
                "id_curso": IDS["id_curso"],
                "nombre_curso": "Estructura de datos",
                "coordinador": "Ana Pérez | Bruno Díaz",
                "creditos": "4",
                "nivel": "05",
                "tipo_curso": "Obligatorio",
                "codigo_curso": "SIS501",
                "id_carrera": IDS["id_carrera"],
            }
        ],
        "silabo.csv": [
            {
                "id_silabo": IDS["id_silabo"],
                "codigo_silabo": "SIS501",
                "sumilla": "Fundamentos de estructuras de datos.",
                "id_curso": IDS["id_curso"],
            }
        ],
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


def _silabos() -> list[dict[str, Any]]:
    return [
        {
            "id_silabo": IDS["id_silabo"],
            "id_curso": IDS["id_curso"],
            "codigo_silabo": "SIS501",
        }
    ]


def test_preview_valida_novedad_y_importa_solo_filas_nuevas(tmp_path: Path) -> None:
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, _filas())
    driver = FakeDriver(
        {
            "cursos": [{"id": IDS["id_curso"]}],
            "carreras": [{"id": IDS["id_carrera"]}],
            "silabos": [{"id": IDS["id_silabo"]}],
        }
    )
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: driver)

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is True
    assert preview["resumen"] == {
        "nuevos_cursos": 1,
        "cursos_actualizados": 0,
        "nuevas_relaciones_curso_silabo": 1,
        "nuevas_competencias": 1,
        "nuevas_habilidades": 1,
        "nuevas_herramientas": 1,
        "nuevas_coberturas": 1,
        "sin_cambios": 0,
    }
    # El resumen lista solo los archivos que son fuente de nodos. `silabo.csv`
    # es contrato público de salida y los nodos Silabo vienen de
    # limpios/silabos.jsonl, así que no aparece acá.
    assert {fila["archivo"]: fila["nuevas"] for fila in preview["archivos"]} == {
        "curso.csv": 1,
        "catalogo_competencias.csv": 1,
        "catalogo_habilidades.csv": 1,
        "catalogo_herramientas.csv": 1,
        "cobertura_curricular.csv": 1,
    }
    resultado = importador.importar(id_ejecucion, preview["fingerprint"], confirmar=True)
    assert resultado["estado"] == "completada"
    assert resultado["id_importacion"].startswith("IMP_")

    revertido = importador.revertir(resultado["id_importacion"], confirmar=True)
    assert revertido["estado"] == "revertida"
    assert revertido["reversion"]["nodos_eliminados"] == 2
    assert "WRITE" in driver.session_obj.modes
    consulta_curso = next(
        consulta for consulta in driver.session_obj.queries if "MERGE (curso:Curso" in consulta
    )
    assert "MERGE (carrera)-[rel:ENSENIA]->(curso)" in consulta_curso
    assert "Silabo" not in consulta_curso
    consulta_silabo = next(
        consulta
        for consulta in driver.session_obj.queries
        if "MERGE (curso)-[rel:TIENE]->(silabo)" in consulta
    )
    assert "UNWIND $rows AS row" in consulta_silabo
    consulta_cobertura = next(
        consulta
        for consulta in driver.session_obj.queries
        if "MERGE (cob:Cobertura_Curricular" in consulta
    )
    assert "-[:TIENE]-(silabo:Silabo" not in consulta_cobertura


def test_preview_rechaza_carrera_inexistente_y_conserva_tiene_curso_silabo(tmp_path: Path) -> None:
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

    assert preview["puede_importar"] is False
    assert any(conflicto["codigo"] == "CARRERA_NO_EXISTE" for conflicto in preview["conflictos"])


def test_preview_rechaza_id_carrera_con_formato_invalido(tmp_path: Path) -> None:
    filas = _filas()
    filas["curso.csv"][0]["id_carrera"] = "CAR_FALSO"
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, filas)
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: FakeDriver())

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is False
    assert any(error["codigo"] == "REFERENCIA_INVALIDA" for error in preview["errores"])


def test_preview_crea_vinculo_curso_silabo_desde_el_silabo_del_mismo_lote(
    tmp_path: Path,
) -> None:
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, _filas())
    driver = FakeDriver(
        {
            "carreras": [{"id": IDS["id_carrera"]}],
            "silabos": [{"id": IDS["id_silabo"]}],
        }
    )
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: driver)

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is True
    assert preview["resumen"]["nuevos_cursos"] == 1
    assert preview["resumen"]["nuevas_relaciones_curso_silabo"] == 1


def test_preview_rechaza_fk_de_silabo_a_curso_inexistente(tmp_path: Path) -> None:
    silabos = _silabos()
    silabos[0]["id_curso"] = "CUR_fedcba9876543210"
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, _filas(), silabos)
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: FakeDriver())

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is False
    assert any(error["codigo"] == "SILABO_CURSO_NO_EXISTE" for error in preview["errores"])


def test_preview_rechaza_codigo_de_silabo_distinto_al_curso(tmp_path: Path) -> None:
    silabos = _silabos()
    silabos[0]["codigo_silabo"] = "SIS999"
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, _filas(), silabos)
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: FakeDriver())

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is False
    assert any(error["codigo"] == "SILABO_CODIGO_CURSO_NO_COINCIDE" for error in preview["errores"])


def test_preview_acepta_codigo_silabo_top_level(tmp_path: Path) -> None:
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, _filas(), _silabos())
    driver = FakeDriver(
        {
            "carreras": [{"id": IDS["id_carrera"]}],
            "silabos": [{"id": IDS["id_silabo"]}],
        }
    )
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: driver)

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is True


def test_preview_acepta_codigo_curso_legacy_del_normalizador(tmp_path: Path) -> None:
    silabos = _silabos()
    silabos[0].pop("codigo_silabo")
    silabos[0]["datos"] = {"codigo_curso": "SIS501"}
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, _filas(), silabos)
    driver = FakeDriver(
        {
            "carreras": [{"id": IDS["id_carrera"]}],
            "silabos": [{"id": IDS["id_silabo"]}],
        }
    )
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: driver)

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is True


def test_preview_acepta_silabo_sin_codigo_para_comparar(tmp_path: Path) -> None:
    silabos = _silabos()
    silabos[0].pop("codigo_silabo")
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, _filas(), silabos)
    driver = FakeDriver(
        {
            "carreras": [{"id": IDS["id_carrera"]}],
            "silabos": [{"id": IDS["id_silabo"]}],
        }
    )
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: driver)

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is True


def test_preview_rechaza_par_de_cobertura_distinto_al_silabo(tmp_path: Path) -> None:
    filas = _filas()
    filas["cobertura_curricular.csv"][0]["id_silabo"] = "SIL_fedcba9876543210"
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, filas)
    driver = FakeDriver(
        {
            "carreras": [{"id": IDS["id_carrera"]}],
            "silabos": [
                {"id": IDS["id_silabo"]},
                {"id": "SIL_fedcba9876543210"},
            ],
        }
    )
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: driver)

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is False
    assert any(
        conflicto["codigo"] == "COBERTURA_PAR_CURSO_SILABO_INVALIDO"
        for conflicto in preview["conflictos"]
    )


def test_preview_acepta_repetir_curso_silabo_en_paquetes_chh_distintos(
    tmp_path: Path,
) -> None:
    filas = _filas()
    filas["cobertura_curricular.csv"].append(
        {
            **filas["cobertura_curricular.csv"][0],
            "id_cob_curricular": "COB_CUR_fedcba9876543210",
            "id_herramienta": "",
        }
    )
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, filas)
    driver = FakeDriver(
        {
            "carreras": [{"id": IDS["id_carrera"]}],
            "silabos": [{"id": IDS["id_silabo"]}],
        }
    )
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: driver)

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is True
    assert preview["resumen"]["nuevas_coberturas"] == 2


def test_preview_acepta_id_de_cobertura(tmp_path: Path) -> None:
    filas = _filas()
    filas["cobertura_curricular.csv"][0]["id_cob_curricular"] = "COB_CUR_fedcba9876543210"
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, filas)
    driver = FakeDriver(
        {
            "carreras": [{"id": IDS["id_carrera"]}],
            "silabos": [{"id": IDS["id_silabo"]}],
        }
    )
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: driver)

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is True


@pytest.mark.parametrize(
    "id_cobertura",
    [
        "COB_CUR_CAN_0123456789abcdef",
        "COB_CUR_SOURCE_0123456789abcdef",
    ],
)
def test_preview_rechaza_variante_de_id_de_cobertura(tmp_path: Path, id_cobertura: str) -> None:
    filas = _filas()
    filas["cobertura_curricular.csv"][0]["id_cob_curricular"] = id_cobertura
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, filas)
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: FakeDriver())

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is False
    assert any(error["codigo"] == "ID_INVALIDO" for error in preview["errores"])


def test_importa_cobertura_sin_habilidad_ni_herramienta(tmp_path: Path) -> None:
    filas = _filas()
    filas["cobertura_curricular.csv"][0].update({"id_habilidad": "", "id_herramienta": ""})
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, filas)
    driver = FakeDriver(
        {
            "carreras": [{"id": IDS["id_carrera"]}],
            "silabos": [{"id": IDS["id_silabo"]}],
        }
    )
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: driver)

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is True
    importador.importar(id_ejecucion, preview["fingerprint"], confirmar=True)
    consulta = next(
        consulta
        for consulta in driver.session_obj.queries
        if "MERGE (cob:Cobertura_Curricular" in consulta
    )
    assert "MATCH (habilidad:Habilidad" not in consulta
    assert "MATCH (herramienta:Herramienta" not in consulta
    assert "[rhb:ENSENIA]" not in consulta
    assert "[rh:ENSENIA]" not in consulta


def test_importa_cobertura_sin_habilidad_con_herramienta(tmp_path: Path) -> None:
    filas = _filas()
    filas["cobertura_curricular.csv"][0]["id_habilidad"] = ""
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, filas)
    driver = FakeDriver(
        {
            "carreras": [{"id": IDS["id_carrera"]}],
            "silabos": [{"id": IDS["id_silabo"]}],
        }
    )
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: driver)

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is True
    importador.importar(id_ejecucion, preview["fingerprint"], confirmar=True)
    consulta = next(
        consulta
        for consulta in driver.session_obj.queries
        if "MERGE (cob:Cobertura_Curricular" in consulta
    )
    assert "MATCH (habilidad:Habilidad" not in consulta
    assert "[rhb:ENSENIA]" not in consulta
    assert "MATCH (herramienta:Herramienta" in consulta
    assert "[rh:ENSENIA]" in consulta


@pytest.mark.parametrize(
    ("campo", "id_inexistente"),
    [
        ("id_competencia", "COMP_fedcba9876543210"),
        ("id_habilidad", "HAB_fedcba9876543210"),
        ("id_herramienta", "HERR_fedcba9876543210"),
    ],
)
def test_preview_rechaza_referencia_chh_fuera_de_catalogo(
    tmp_path: Path,
    campo: str,
    id_inexistente: str,
) -> None:
    filas = _filas()
    filas["cobertura_curricular.csv"][0][campo] = id_inexistente
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, filas)
    driver = FakeDriver(
        {
            "carreras": [{"id": IDS["id_carrera"]}],
            "silabos": [{"id": IDS["id_silabo"]}],
        }
    )
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: driver)

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is False
    assert any(
        conflicto["codigo"] == "REFERENCIA_CATALOGO_NO_EXISTE"
        for conflicto in preview["conflictos"]
    )


def _curso_existente(**sobrescrituras: str) -> dict[str, str]:
    return {
        "id_curso": IDS["id_curso"],
        "nombre_curso": "Estructura de datos",
        "coordinador": "Ana Pérez | Bruno Díaz",
        "creditos": "4",
        "nivel": "05",
        "tipo_curso": "Obligatorio",
        "codigo_curso": "SIS501",
        "id_carrera": IDS["id_carrera"],
        **sobrescrituras,
    }


def test_repara_ensenia_faltante_para_curso_existente_exacto(tmp_path: Path) -> None:
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, _filas())
    driver = FakeDriver(
        {
            "cursos": [{"id": IDS["id_curso"]}],
            "cursos_detalle": [_curso_existente()],
            "carreras": [{"id": IDS["id_carrera"]}],
            "silabos": [{"id": IDS["id_silabo"]}],
            "pares": [{"id_curso": IDS["id_curso"], "id_silabo": IDS["id_silabo"]}],
        }
    )
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: driver)

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is True
    assert preview["resumen"]["cursos_actualizados"] == 1
    resultado = importador.importar(id_ejecucion, preview["fingerprint"], confirmar=True)
    assert resultado["estado"] == "completada"
    consulta = next(
        consulta
        for consulta in driver.session_obj.queries
        if "MERGE (carrera)-[rel:ENSENIA]->(curso)" in consulta
    )
    assert "ON CREATE SET rel._ciar_import_id" in consulta


def test_curso_existente_con_ensenia_no_escribe_nada(tmp_path: Path) -> None:
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, _filas())
    driver = FakeDriver(
        {
            "cursos": [{"id": IDS["id_curso"]}],
            "cursos_detalle": [_curso_existente()],
            "carreras": [{"id": IDS["id_carrera"]}],
            "silabos": [{"id": IDS["id_silabo"]}],
            "pares": [{"id_curso": IDS["id_curso"], "id_silabo": IDS["id_silabo"]}],
            "pares_carrera_curso": [{"id_carrera": IDS["id_carrera"], "id_curso": IDS["id_curso"]}],
        }
    )
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: driver)

    preview = importador.previsualizar(id_ejecucion)

    assert preview["resumen"]["cursos_actualizados"] == 0
    resultado = importador.importar(id_ejecucion, preview["fingerprint"], confirmar=True)
    assert resultado["estado"] == "completada"
    assert not any("MERGE (curso:Curso" in consulta for consulta in driver.session_obj.queries)


def test_reversion_restaura_propiedades_de_curso_preexistente(tmp_path: Path) -> None:
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, _filas())
    driver = FakeDriver(
        {
            "cursos": [{"id": IDS["id_curso"]}],
            "cursos_detalle": [_curso_existente(coordinador="")],
            "carreras": [{"id": IDS["id_carrera"]}],
            "silabos": [{"id": IDS["id_silabo"]}],
            "pares": [{"id_curso": IDS["id_curso"], "id_silabo": IDS["id_silabo"]}],
            "pares_carrera_curso": [{"id_carrera": IDS["id_carrera"], "id_curso": IDS["id_curso"]}],
            "restauraciones": [{"total": 1}],
        }
    )
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: driver)

    preview = importador.previsualizar(id_ejecucion)
    assert preview["resumen"]["cursos_actualizados"] == 1
    resultado = importador.importar(id_ejecucion, preview["fingerprint"], confirmar=True)
    revertido = importador.revertir(resultado["id_importacion"], confirmar=True)

    assert revertido["reversion"]["propiedades_restauradas"] == 1
    consulta_escritura = next(
        consulta
        for consulta in driver.session_obj.queries
        if "CiarImportacionCursoReversion" in consulta and "UNWIND $rows" in consulta
    )
    assert "propiedades_presentes" in consulta_escritura
    consulta_reversion = next(
        consulta
        for consulta in driver.session_obj.queries
        if "CiarImportacionCursoReversion" in consulta and "curso.coordinador = CASE" in consulta
    )
    assert "DELETE curso" not in consulta_reversion
    assert "curso.coordinador = CASE" in consulta_reversion
    assert any(
        "CiarImportacionCursoReversion" in consulta and "DELETE reversion" in consulta
        for consulta in driver.session_obj.queries
    )


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
        conflicto["codigo"] == "NOMBRE_EXISTENTE_CON_OTRO_ID" for conflicto in preview["conflictos"]
    )


def test_preview_bloquea_cobertura_sin_padres_curriculares(tmp_path: Path) -> None:
    gestor, id_ejecucion = _manifest_y_salidas(tmp_path, _filas())
    importador = ImportadorNeo4j(gestor, driver_factory=lambda: FakeDriver())

    preview = importador.previsualizar(id_ejecucion)

    assert preview["puede_importar"] is False
    assert any(
        conflicto["codigo"] == "REFERENCIA_PARENT_NO_EXISTE" for conflicto in preview["conflictos"]
    )
