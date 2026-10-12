"""Pruebas focalizadas del flujo de empleabilidad con el índice HAB_TEC."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from agente.normalizador.empleabilidad.pipeline import normalizar_staging
from agente.normalizador.modelos import ResultadoValidacionEntrada


class _RetrieverFalso:
    modelo = "qwen3-embedding:0.6b"
    documentos = (object(),)

    def buscar(self, _texto: str, carrera: str):
        return (
            SimpleNamespace(
                id_habilidad="HAB_TEC_1",
                nombre="Análisis financiero",
                descripcion="Analizar estados financieros",
                similitud=0.91,
                carrera=carrera,
            ),
        )


def test_normaliza_oferta_con_vecino_hab_tec_sin_catalogos_chh(tmp_path: Path) -> None:
    (tmp_path / "limpios").mkdir()
    registro = {
        "id_registro": "pub_1",
        "universo": "publicaciones",
        "origen": {"hoja": "2025", "fila": 3},
        "datos": {
            "ruc": "20100000000",
            "razon_social": "Empresa Uno",
            "carrera_resumen": "Economía",
            "cargo": "Analista",
            "posicion_a_publicar": "Analista financiero",
            "area": "Finanzas",
            "funciones": "Analizar estados financieros",
        },
    }
    (tmp_path / "limpios" / "publicaciones.jsonl").write_text(
        json.dumps(registro, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    resultado = normalizar_staging(
        tmp_path,
        ResultadoValidacionEntrada("fuente.xlsx", "hash", True, (), ()),
        hab_tec_retriever=_RetrieverFalso(),
    )

    assert resultado.publicable is True
    assert resultado.relaciones == 1
    requerimientos = (tmp_path / "salidas" / "requerimiento_laboral.csv").read_text(
        encoding="utf-8-sig"
    )
    assert "HAB_TEC_1" in requerimientos
    resumen = json.loads(
        (tmp_path / "salidas" / "reportes" / "resumen.json").read_text(encoding="utf-8")
    )
    assert resumen["motor_habilidades"] == "hab_tec_qwen_vectorial"
