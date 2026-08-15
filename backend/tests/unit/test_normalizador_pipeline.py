"""Pruebas del paquete candidato, cuarentena y gate de publicación."""

from __future__ import annotations

import json
from pathlib import Path

from agente.normalizador.empleabilidad.catalogo import CatalogoCHH
from agente.normalizador.empleabilidad.pipeline import normalizar_staging
from agente.normalizador.modelos import ResultadoValidacionEntrada


def _catalogo(tmp_path: Path) -> CatalogoCHH:
    matches = tmp_path / "matches"
    matches.mkdir(parents=True)
    (matches / "catalogo_competencias.csv").write_text(
        "id_competencia,nombre_competencia,descripcion_breve_competencia,tipo_competencia\n"
        "COMP_1,Análisis de datos,Analizar información,dura\n",
        encoding="utf-8",
    )
    (matches / "catalogo_habilidades.csv").write_text(
        "id_habilidad,nombre_habilidad,descripcion_breve\n"
        "HAB_1,Analizar datos para obtener hallazgos,Analizar datos\n",
        encoding="utf-8",
    )
    (matches / "catalogo_herramientas.csv").write_text(
        "id_herramienta,nombre_herramienta,descripcion_breve_herramienta\n"
        "HERR_1,SQL,Consultas de datos\n",
        encoding="utf-8",
    )
    return CatalogoCHH.desde_directorio(tmp_path)


def _validacion() -> ResultadoValidacionEntrada:
    return ResultadoValidacionEntrada("fuente.xlsx", "hash", True, (), ())


def _registro(id_registro: str, datos: dict[str, object]) -> dict[str, object]:
    return {
        "id_registro": id_registro,
        "universo": "publicaciones",
        "origen": {"hoja": "Publicaciones 2030", "fila": 6},
        "datos": datos,
    }


def test_genera_paquete_publicable_y_evidencia(tmp_path: Path) -> None:
    catalogo = _catalogo(tmp_path / "catalogos")
    ejecucion = tmp_path / "ejecucion"
    limpios = ejecucion / "limpios"
    limpios.mkdir(parents=True)
    fila = _registro(
        "publicacion_1",
        {
            "ruc": "20100000000",
            "razon_social": "Empresa Uno",
            "posicion_a_publicar": "Analista de datos",
            "cargo": "Analista",
            "area": "Sistemas",
            "funciones": "Analizar datos usando SQL",
            "fecha_de_publicacion": "2030-01-01",
            "fecha_de_finalizacion": "2030-01-31",
        },
    )
    (limpios / "publicaciones.jsonl").write_text(
        json.dumps(fila, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    resultado = normalizar_staging(ejecucion, _validacion(), catalogo)

    assert resultado.publicable is True
    assert resultado.relaciones == 1
    assert resultado.cuarentena == 0
    assert "HERR_1" in (ejecucion / "salidas" / "requerimiento_laboral.csv").read_text(
        encoding="utf-8-sig"
    )
    assert (ejecucion / "salidas" / "reportes" / "evidencias_chh.jsonl").exists()


def test_no_publica_oferta_sin_cadena(tmp_path: Path) -> None:
    catalogo = _catalogo(tmp_path / "catalogos")
    ejecucion = tmp_path / "ejecucion"
    limpios = ejecucion / "limpios"
    limpios.mkdir(parents=True)
    fila = _registro(
        "publicacion_2",
        {
            "ruc": "20100000000",
            "razon_social": "Empresa Uno",
            "posicion_a_publicar": "Practicante",
            "area": "",
            "funciones": "",
        },
    )
    (limpios / "publicaciones.jsonl").write_text(
        json.dumps(fila, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    resultado = normalizar_staging(ejecucion, _validacion(), catalogo)

    assert resultado.publicable is False
    assert resultado.cuarentena == 1
    assert any(hallazgo.codigo == "OFERTA_SIN_REQUISITO" for hallazgo in resultado.hallazgos)
