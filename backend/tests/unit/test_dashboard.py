"""Pruebas aisladas de contratos y defensas del dashboard."""

from __future__ import annotations

from datetime import date

import pytest

from agente.dashboard import servicio
from agente.dashboard.consultas import todas_las_plantillas
from agente.guardas.cypher import validar_seguridad_basica


def test_todas_las_plantillas_son_lecturas_seguras() -> None:
    assert len(todas_las_plantillas()) == 17
    for consulta in todas_las_plantillas().values():
        assert validar_seguridad_basica(consulta) == []


def test_periodo_rechaza_orden_invalido_y_rango_excesivo() -> None:
    with pytest.raises(servicio.ErrorDashboard, match="inicial"):
        servicio._parametros_periodo(date(2025, 2, 1), date(2025, 1, 1))
    with pytest.raises(servicio.ErrorDashboard, match="diez años"):
        servicio._parametros_periodo(date(2010, 1, 1), date(2025, 1, 1))


def test_cobertura_sin_cursos_no_se_convierte_en_cero(monkeypatch) -> None:
    monkeypatch.setattr(
        servicio,
        "obtener_carrera",
        lambda _id: {
            "id": "CAR_1",
            "nombre": "Carrera sin carga",
            "cursos_conectados": 0,
            "cobertura_disponible": False,
        },
    )

    respuesta = servicio.cobertura_dimension("competencias", "CAR_1")

    assert respuesta["disponible"] is False
    assert respuesta["filas"] == []
    assert "no tiene cursos" in str(respuesta["motivo"]).lower()


def test_brechas_normaliza_resultados(monkeypatch) -> None:
    monkeypatch.setattr(servicio, "verificar_plantillas", lambda: None)
    monkeypatch.setattr(
        servicio,
        "obtener_carrera",
        lambda _id: {
            "id": "CAR_1",
            "nombre": "Sistemas",
            "cursos_conectados": 4,
            "cobertura_disponible": True,
        },
    )
    monkeypatch.setattr(
        servicio,
        "ejecutar_lectura",
        lambda _consulta, _parametros: [
            {
                "id": "COMP_1",
                "elemento": "Python",
                "cursos_con_cobertura": 1,
                "total_cursos": 4,
                "ofertas_que_requieren": 6,
                "total_ofertas": 10,
                "cobertura": 0.25,
                "demanda": 0.6,
                "brecha": 0.35,
            }
        ],
    )

    respuesta = servicio.brechas_dimension(
        "competencias",
        "CAR_1",
        date(2024, 1, 1),
        date(2024, 12, 31),
    )

    assert respuesta["disponible"] is True
    assert respuesta["filas"][0]["brecha"] == 0.35
    assert respuesta["filas"][0]["total_ofertas"] == 10
