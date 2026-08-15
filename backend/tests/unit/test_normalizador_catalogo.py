"""Pruebas del registro CHH y del contexto acotado para el LLM."""

from __future__ import annotations

from pathlib import Path

import pytest

from agente.normalizador.empleabilidad.catalogo import (
    CatalogoCHH,
    cargar_catalogo_carrera,
    clave_concepto,
)
from agente.normalizador.silabos.perfiles import crear_perfil_bootstrap


def _crear_catalogos(directorio: Path) -> None:
    matches = directorio / "matches"
    matches.mkdir(parents=True)
    (matches / "catalogo_competencias.csv").write_text(
        "id_competencia,nombre_competencia,descripcion_breve_competencia,tipo_competencia\n"
        "COMP_1,Análisis de datos,Interpretar información, dura\n",
        encoding="utf-8",
    )
    (matches / "catalogo_habilidades.csv").write_text(
        "id_habilidad,nombre_habilidad,descripcion_breve\n"
        "HAB_1,Analizar datos,Ejecutar análisis de datos\n",
        encoding="utf-8",
    )
    (matches / "catalogo_herramientas.csv").write_text(
        "id_herramienta,nombre_herramienta,descripcion_breve_herramienta\n"
        "HERR_1,Power BI,Crear visualizaciones\n",
        encoding="utf-8",
    )
    empleabilidad = directorio / "empleabilidad"
    empleabilidad.mkdir()
    (empleabilidad / "requerimiento_laboral.csv").write_text(
        "id_req_laboral,id_oferta_laboral,id_puesto,id_empresa,id_competencia,"
        "id_habilidad,id_herramienta,tipo\n"
        "REQ_1,OFE_1,PUE_1,EMP_1,COMP_1,HAB_1,HERR_1,exige\n",
        encoding="utf-8",
    )


def test_carga_contexto_y_ejemplo_chh(tmp_path: Path) -> None:
    _crear_catalogos(tmp_path)

    catalogo = CatalogoCHH.desde_directorio(tmp_path)
    contexto = catalogo.contexto_llm("analizar datos")

    assert catalogo.resumen()["competencias"] == 1
    assert contexto["version_catalogo"]
    assert contexto["candidatos"]["habilidad"][0]["id"] == "HAB_1"  # type: ignore[index]
    assert contexto["ejemplos"][0]["herramienta"]["id"] == "HERR_1"  # type: ignore[index]


def test_clave_conserva_signos_de_herramienta() -> None:
    assert clave_concepto("C++") == "c++"
    assert clave_concepto("Node.js") == "node.js"


def test_carga_catalogo_directo_de_carrera(tmp_path: Path) -> None:
    directorio = tmp_path / "carreras" / "MARKETING" / "2026-1"
    directorio.mkdir(parents=True)
    (directorio / "catalogo_competencias.csv").write_text(
        "id_competencia,nombre_competencia,descripcion_breve_competencia,tipo_competencia\n"
        "COMP_MARK,Gestión estratégica,Diseñar estrategias de marketing,dura\n",
        encoding="utf-8",
    )
    (directorio / "catalogo_habilidades.csv").write_text(
        "id_habilidad,nombre_habilidad,descripcion_breve\n"
        "HAB_MARK,Diseñar estrategias,Ejecutar diseño estratégico\n",
        encoding="utf-8",
    )
    (directorio / "catalogo_herramientas.csv").write_text(
        "id_herramienta,nombre_herramienta,descripcion_breve_herramienta\n"
        "HERR_MARK,Google Analytics,Analizar métricas\n",
        encoding="utf-8",
    )

    catalogo = cargar_catalogo_carrera("Marketing", "2026-1", str(tmp_path))

    assert catalogo is not None
    assert catalogo.obtener("competencia", "Gestión estratégica") is not None
    assert catalogo.obtener("herramienta", "Google Analytics") is not None


def test_crea_perfil_bootstrap_sin_alterar_los_esquemas_csv(tmp_path: Path) -> None:
    ejecucion = tmp_path / "NOR_TEST" / "salidas"
    ejecucion.mkdir(parents=True)
    (ejecucion / "catalogo_competencias.csv").write_text(
        "id_competencia,nombre_competencia,descripcion_breve_competencia,tipo_competencia\n"
        "COMP_MARK,Gestión estratégica,Diseñar estrategias de marketing,dura\n",
        encoding="utf-8-sig",
    )
    (ejecucion / "catalogo_habilidades.csv").write_text(
        "id_habilidad,nombre_habilidad,descripcion_breve\n"
        "HAB_MARK,Diseñar estrategias,Diseñar estrategias de marketing\n",
        encoding="utf-8-sig",
    )
    (ejecucion / "catalogo_herramientas.csv").write_text(
        "id_herramienta,nombre_herramienta,descripcion_breve_herramienta\n"
        "HERR_MARK,Google Analytics,Analizar métricas\n",
        encoding="utf-8-sig",
    )
    (ejecucion / "cobertura_curricular.csv").write_text(
        "id_cob_curricular,id_curso,id_silabo,id_competencia,id_habilidad,id_herramienta\n"
        "COB_1,CUR_1,SIL_1,COMP_MARK,HAB_MARK,HERR_MARK\n",
        encoding="utf-8-sig",
    )
    reportes = ejecucion / "reportes"
    reportes.mkdir()
    (reportes / "habilidades_fuente.jsonl").write_text(
        '{"id_habilidad_fuente":"SRC_1","estado_resolucion":"REVISAR"}\n',
        encoding="utf-8",
    )

    perfil = crear_perfil_bootstrap(
        ejecucion.parent,
        tmp_path / "catalogos",
        "Marketing",
        "2026-1",
    )

    assert perfil.competencias == 1
    assert perfil.habilidades_pendientes == 1
    directorio = tmp_path / "catalogos" / "carreras" / "MARKETING" / "2026-1"
    assert (directorio / "perfil.json").is_file()
    assert (
        directorio / "reportes" / "habilidades_pendientes.jsonl"
    ).read_text(encoding="utf-8").strip()
    catalogo = cargar_catalogo_carrera("Marketing", "2026-1", str(tmp_path / "catalogos"))
    assert catalogo is not None
    assert catalogo.obtener("herramienta", "Google Analytics") is not None


def test_rechaza_id_duplicado_en_catalogo(tmp_path: Path) -> None:
    _crear_catalogos(tmp_path)
    ruta = tmp_path / "matches" / "catalogo_habilidades.csv"
    ruta.write_text(
        "id_habilidad,nombre_habilidad,descripcion_breve\n"
        "HAB_1,Analizar datos,Ejecutar análisis de datos\n"
        "HAB_1,Resolver datos,Resolver problemas de datos\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="ID duplicado"):
        CatalogoCHH.desde_directorio(tmp_path)


def test_rechaza_colision_de_nombre_normalizado(tmp_path: Path) -> None:
    _crear_catalogos(tmp_path)
    ruta = tmp_path / "matches" / "catalogo_habilidades.csv"
    ruta.write_text(
        "id_habilidad,nombre_habilidad,descripcion_breve\n"
        "HAB_1,Gestion de datos,Ejecutar análisis de datos\n"
        "HAB_2,Gestión de datos,Interpretar información de datos\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="colisiona"):
        CatalogoCHH.desde_directorio(tmp_path)
