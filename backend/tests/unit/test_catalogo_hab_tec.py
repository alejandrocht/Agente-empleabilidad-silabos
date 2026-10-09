from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from openpyxl import Workbook

from agente.api import normalizador, servidor
from agente.normalizador.catalogo_hab_tec import GestorCatalogosHabTec


def _excel(ruta: Path, filas: list[tuple[str, str, str, str]]) -> None:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "HAB_TEC"
    hoja.append(["Carrera", "id", "nombre", "descripcion"])
    for fila in filas:
        hoja.append(fila)
    libro.save(ruta)


def test_valida_asociaciones_inmutables_y_preserva_preview(tmp_path: Path) -> None:
    fuente = tmp_path / "catalogo.xlsx"
    _excel(
        fuente,
        [
            (
                "Ingeniería de Sistemas",
                "HAB_TEC_001",
                "Inteligencia Artificial",
                "Modelos predictivos",
            ),
            ("Ingeniería de Sistemas", "HAB_TEC_001", "Machine Learning", "Modelos entrenados"),
        ],
    )
    gestor = GestorCatalogosHabTec(tmp_path / "catalogos")

    estado = gestor.crear_desde_archivo("catalogo.xlsx", fuente)

    assert estado["estado"] == "rechazado"
    assert estado["resumen"]["errores"] == 1
    assert estado["preview"][0]["id"] == "HAB_TEC_001"
    assert estado["hallazgos"][0]["codigo"] == "HAB_TEC_ASOCIACION_DUPLICADA"


def test_acepta_un_hab_tec_en_varias_carreras(tmp_path: Path) -> None:
    fuente = tmp_path / "catalogo.xlsx"
    _excel(
        fuente,
        [
            ("Administración", "HAB_TEC_001", "Gestión de proyectos", "Planificación general"),
            ("Arquitectura", "HAB_TEC_001", "Gestión de proyectos", "Planificación de obra"),
        ],
    )
    gestor = GestorCatalogosHabTec(tmp_path / "catalogos")

    estado = gestor.crear_desde_archivo("catalogo.xlsx", fuente)

    assert estado["estado"] == "listo_para_vectorizar"
    assert estado["resumen"]["habilidades"] == 2
    assert estado["resumen"]["errores"] == 0


def test_admite_un_id_hab_tec_con_nombres_distintos_como_advertencia(tmp_path: Path) -> None:
    fuente = tmp_path / "catalogo.xlsx"
    _excel(
        fuente,
        [
            ("Administración", "HAB_TEC_001", "Gestión de proyectos", "Planificación"),
            ("Arquitectura", "HAB_TEC_001", "Project management", "Planificación de obra"),
        ],
    )
    gestor = GestorCatalogosHabTec(tmp_path / "catalogos")

    estado = gestor.crear_desde_archivo("catalogo.xlsx", fuente)

    assert estado["estado"] == "listo_para_vectorizar"
    assert estado["resumen"]["errores"] == 0
    assert estado["hallazgos"][0]["codigo"] == "HAB_TEC_ID_NOMBRE_VARIANTE"


def test_vectoriza_y_persiste_indice_local(tmp_path: Path, monkeypatch) -> None:
    fuente = tmp_path / "catalogo.xlsx"
    _excel(
        fuente,
        [
            (
                "Ingeniería de Sistemas",
                "HAB_TEC_001",
                "Inteligencia Artificial",
                "Modelos predictivos",
            ),
            ("Ingeniería de Sistemas", "HAB_TEC_002", "Python", "Programación para datos"),
        ],
    )
    publicaciones: list[tuple[list[object], str]] = []
    gestor = GestorCatalogosHabTec(
        tmp_path / "catalogos",
        publicar_en_neo4j=lambda registros, id_catalogo: (
            publicaciones.append((list(registros), id_catalogo))
            or {"habilidades": 2, "asociaciones": 2}
        ),
    )
    estado = gestor.crear_desde_archivo("catalogo.xlsx", fuente)
    catalogo = gestor._obtener(str(estado["id_catalogo"]))
    catalogo.modelo_embedding = "qwen3-embedding:0.6b"
    monkeypatch.setattr(
        gestor,
        "_embeddings",
        lambda _endpoint, _modelo, textos: [
            [float(numero), 0.25] for numero, _ in enumerate(textos, 1)
        ],
    )

    gestor._vectorizar(catalogo)

    assert gestor.obtener(catalogo.id_catalogo)["estado"] == "vectorizado"
    assert len(publicaciones) == 1
    assert publicaciones[0][0][0].id_hab_tec == "HAB_TEC_001"
    assert gestor.obtener(catalogo.id_catalogo)["resumen"]["neo4j"] == {
        "habilidades": 2,
        "asociaciones": 2,
    }
    assert (catalogo.directorio / "indice" / "vectores.f32").stat().st_size == 16
    assert (catalogo.directorio / "indice" / "metadatos.jsonl").is_file()
    reiniciado = GestorCatalogosHabTec(tmp_path / "catalogos")
    assert reiniciado.obtener(catalogo.id_catalogo)["resumen"]["dimension_embedding"] == 2


def test_endpoint_carga_y_expone_catalogo_hab_tec(tmp_path: Path, monkeypatch) -> None:
    fuente = tmp_path / "catalogo.xlsx"
    _excel(
        fuente,
        [("Ingeniería de Sistemas", "HAB_TEC_001", "Python", "Programación")],
    )
    monkeypatch.setattr(
        normalizador,
        "gestor_catalogos_hab_tec",
        GestorCatalogosHabTec(tmp_path / "catalogos"),
    )
    cliente = TestClient(servidor.app, client=("127.0.0.1", 0))

    respuesta = cliente.post(
        "/normalizador/catalogos/hab-tec",
        files={
            "archivo": (
                "catalogo.xlsx",
                BytesIO(fuente.read_bytes()),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert respuesta.status_code == 202
    datos = respuesta.json()
    assert datos["estado"] == "listo_para_vectorizar"
    detalle = cliente.get(f"/normalizador/catalogos/hab-tec/{datos['id_catalogo']}")
    assert detalle.status_code == 200
    assert detalle.json()["preview"][0]["id"] == "HAB_TEC_001"
