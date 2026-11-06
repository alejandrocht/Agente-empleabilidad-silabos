import csv
from pathlib import Path

import pytest

from agente.normalizador.silabos import exportacion_deterministica as exportador
from agente.normalizador.silabos.extraccion_curricular import _hash_id


def test_consolida_carreras_sin_llm_ni_habilidades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    origen = tmp_path / "silabos"
    for carrera in ("ADMINISTRACION", "DERECHO"):
        carpeta = origen / carrera / "2026-2" / "Ciclo_01"
        carpeta.mkdir(parents=True)
        (carpeta / "ETICA.docx").touch()
        if carrera == "ADMINISTRACION":
            (carpeta / "OTRO_CURSO.docx").touch()
    (origen / "silabs_errores").mkdir()
    (origen / "silabs_errores" / "MALO.docx").touch()
    generales = origen / "ESTUDIOS_GENERALES" / "2026-2" / "Ciclo_01"
    generales.mkdir(parents=True)
    (generales / "ETICA.docx").touch()

    def extraer(ruta: Path, nombre: str, carrera: str, periodo: str) -> dict[str, object]:
        return {
            "id_curso": _hash_id("CUR", "101"),
            "id_silabo": _hash_id("SIL", "101", periodo),
            "carrera": carrera,
            "periodo": periodo,
            "datos": {
                "codigo_curso": "101",
                "nombre_curso": f"{nombre} {carrera}",
                "competencias_declaradas": [
                    {
                        "nombre": (
                            "Pensamiento crítico"
                            if carrera == "ADMINISTRACION"
                            else "Pensamiento critico"
                        ),
                        "descripcion": "Argumenta",
                        "codigo": "G1",
                        "tipo": "generica",
                    }
                ],
                "logro_general": "Comprender el tema",
                "logros_especificos": [
                    {
                        "descripcion": "Aplicar el tema",
                        "codigos_competencia": ["G1"],
                    }
                ],
            },
        }

    monkeypatch.setattr(exportador, "_extraer_docx", extraer)
    salida = tmp_path / "resultado"
    resumen = exportador.exportar(origen, salida)
    assert resumen["carreras"] == 2
    assert resumen["silabos_fuente"] == 3
    assert {archivo.name for archivo in salida.iterdir()} == set(exportador.ARCHIVOS)

    def leer(nombre: str) -> list[dict[str, str]]:
        with (salida / nombre).open(encoding="utf-8-sig", newline="") as archivo:
            return list(csv.DictReader(archivo))

    cursos, silabos = leer("curso.csv"), leer("silabo.csv")
    competencias, logros = leer("catalogo_competencias.csv"), leer("catalogo_logros.csv")
    coberturas = leer("cobertura_curricular.csv")
    assert len(cursos) == len(silabos) == 3
    assert len(competencias) == 1
    assert len(logros) == 6
    assert len(coberturas) == 6
    assert len({fila["id_carrera"] for fila in cursos}) == 2
    assert _hash_id("CAR", "ESTUDIOS_GENERALES") not in {fila["id_carrera"] for fila in cursos}
    assert {fila["id_curso"] for fila in silabos} == {fila["id_curso"] for fila in cursos}
    assert {fila["id_logro"] for fila in coberturas} == {fila["id_logro"] for fila in logros}
    assert {fila["id_competencia"] for fila in coberturas} == {
        fila["id_competencia"] for fila in competencias
    }
