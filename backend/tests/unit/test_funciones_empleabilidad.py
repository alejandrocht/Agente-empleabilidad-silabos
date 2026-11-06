from __future__ import annotations

import json
from pathlib import Path

import pytest

from agente.normalizador.empleabilidad.funciones import funciones_concretas
from agente.normalizador.empleabilidad.neo4j import ImportadorEmpleabilidadNeo4j
from agente.normalizador.empleabilidad.pipeline import normalizar_staging
from agente.normalizador.modelos import ResultadoValidacionEntrada


@pytest.mark.parametrize(
    "texto",
    [
        None,
        "",
        "Inherentes al puesto",
        "Inherentes al puesto.",
        "Inherentes al puetso.",
        "Funciones inherentes al cargo",
        "Función inherente al puesto",
        "Funciones: inherentes a la posición",
        "Otra función asignada por su jefe inmediato.",
        "Otras funciones inherentes al ámbito de su competencia.",
        "Cumplir con otras responsabilidades inherentes al cargo.",
        "Otras funciones asignadas por su jefe inmediato.",
    ],
)
def test_frases_genericas_no_son_evidencia(texto):
    assert funciones_concretas(texto) == ""


def test_conserva_funciones_concretas_y_descarta_clausula_generica():
    texto = (
        "Aplicar buenas prácticas de desarrollo para css, javascript y html. "
        "Otras labores inherentes al cargo."
    )
    assert funciones_concretas(texto) == (
        "Aplicar buenas prácticas de desarrollo para css, javascript y html."
    )
    assert funciones_concretas("Analizar riesgos inherentes al proyecto.")
    assert funciones_concretas(
        "Otras funciones inherentes al puesto, incluyendo analizar estados financieros."
    )


def test_importador_rechaza_requerimiento_generico_incluso_desde_csv_antiguo():
    filas = {
        "oferta_laboral.csv": [
            {"id_ofe_laboral": "LAB_1", "descripcion_breve": "Inherentes al puesto"},
            {"id_ofe_laboral": "LAB_2", "descripcion_breve": "Diseñar interfaces de usuario."},
        ],
        "requerimiento_laboral.csv": [
            {"id_oferta_laboral": "LAB_1"},
            {"id_oferta_laboral": "LAB_2"},
        ],
    }
    validas, rechazadas = ImportadorEmpleabilidadNeo4j._ofertas_publicables(filas)
    assert [r["id_ofe_laboral"] for r in validas] == ["LAB_2"]
    assert [r["id_ofe_laboral"] for r in rechazadas] == ["LAB_1"]
    filas["requerimiento_laboral.csv"] = []
    assert ImportadorEmpleabilidadNeo4j._ofertas_publicables(filas)[0] == []


def test_pipeline_no_consulta_modelo_ni_crea_relaciones_sin_funciones(tmp_path: Path):
    class Retriever:
        modelo = "no-debe-consultarse"
        documentos = (object(),)

        def buscar(self, *args):
            raise AssertionError("No se debe inferir por el cargo o el área")

    (tmp_path / "limpios").mkdir()
    registro = {
        "id_registro": "pub_1",
        "universo": "publicaciones",
        "origen": {},
        "datos": {
            "ruc": "20100000000",
            "razon_social": "Empresa",
            "posicion_a_publicar": "Ingeniero civil",
            "area": "Ingeniería",
            "carrera_resumen": "Ingeniería Civil",
            "funciones": "Inherentes al puesto.",
        },
    }
    (tmp_path / "limpios/publicaciones.jsonl").write_text(json.dumps(registro) + "\n")
    resultado = normalizar_staging(
        tmp_path,
        ResultadoValidacionEntrada("fuente.xlsx", "hash", True, (), ()),
        hab_tec_retriever=Retriever(),
    )
    assert resultado.relaciones == 0
    assert any(h.codigo == "OFERTA_SIN_FUNCIONES_CONCRETAS" for h in resultado.hallazgos)
    cuarentena = json.loads((tmp_path / "salidas/reportes/cuarentena.jsonl").read_text())
    assert cuarentena["datos"]["funciones"] == "Inherentes al puesto."
