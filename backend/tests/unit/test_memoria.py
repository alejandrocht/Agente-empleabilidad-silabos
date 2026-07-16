"""Auditoría de slots vivos, TTL y resúmenes cada doce turnos."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agente.memoria import bloques, conversacional


def test_entidad_actualiza_slot_y_formato() -> None:
    conversacional.actualizar_entidades(
        "sesion",
        [{"label": "Carrera", "nombre": "INGENIERIA DE SISTEMAS", "id": "CAR_1"}],
    )

    memoria = conversacional.obtener("sesion")

    assert memoria["entidades_activas"]["Carrera"]["id"] == "CAR_1"
    assert "INGENIERIA DE SISTEMAS" in conversacional.formatear("sesion")


def test_historial_conserva_cambios_sin_duplicar_la_misma_entidad() -> None:
    sistemas = {"label": "Carrera", "nombre": "INGENIERIA DE SISTEMAS", "id": "CAR_1"}
    industrial = {"label": "Carrera", "nombre": "INGENIERIA INDUSTRIAL", "id": "CAR_2"}

    conversacional.actualizar_entidades("sesion", [sistemas])
    conversacional.actualizar_entidades("sesion", [sistemas])
    conversacional.actualizar_entidades("sesion", [sistemas])
    conversacional.actualizar_entidades("sesion", [industrial])

    memoria = conversacional.obtener("sesion")
    historial = conversacional.historial_entidades("sesion")["Carrera"]

    assert memoria["entidades_activas"]["Carrera"]["id"] == "CAR_2"
    assert [entidad["id"] for entidad in historial] == ["CAR_1", "CAR_2"]
    assert "INGENIERIA DE SISTEMAS -> INGENIERIA INDUSTRIAL" in conversacional.formatear(
        "sesion"
    )


def test_historial_respeta_limite_configurado(monkeypatch) -> None:
    monkeypatch.setattr(conversacional, "_LIMITE_HISTORIAL", 2)
    for indice in range(3):
        conversacional.actualizar_entidades(
            "sesion",
            [{"label": "Carrera", "nombre": f"CARRERA {indice}", "id": f"CAR_{indice}"}],
        )

    historial = conversacional.historial_entidades("sesion")["Carrera"]
    assert [entidad["id"] for entidad in historial] == ["CAR_1", "CAR_2"]


def test_memoria_vencida_se_reinicia(monkeypatch) -> None:
    monkeypatch.setattr(conversacional, "_TTL", 10)
    conversacional.actualizar_entidades("sesion", [{"label": "Carrera", "id": "CAR_1"}])
    conversacional._CACHE["sesion"]["updated_at"] = (
        datetime.now(UTC) - timedelta(seconds=11)
    ).isoformat()

    memoria = conversacional.obtener("sesion")
    assert memoria["entidades_activas"] == {}
    assert memoria["historial_entidades"] == {}


def test_bloque_se_resume_al_turno_doce(monkeypatch) -> None:
    monkeypatch.setattr(bloques, "_resumir", lambda turnos: f"Resumen de {len(turnos)} turnos")
    for indice in range(12):
        bloques.registrar_mensaje("sesion", f"Pregunta {indice}", f"Respuesta {indice}")

    assert bloques.obtener_bloques("sesion") == ["Resumen de 12 turnos"]


def test_fallo_de_resumen_repone_los_turnos(monkeypatch) -> None:
    monkeypatch.setattr(bloques, "_CADA", 2)

    def fallar(_turnos):
        raise RuntimeError("servicio temporalmente no disponible")

    monkeypatch.setattr(bloques, "_resumir", fallar)
    bloques.registrar_mensaje("sesion", "Pregunta 1", "Respuesta 1")
    bloques.registrar_mensaje("sesion", "Pregunta 2", "Respuesta 2")

    assert len(bloques._CACHE["sesion"]["pendientes"]) == 2
    assert bloques._CACHE["sesion"]["contador"] == 2

    monkeypatch.setattr(bloques, "_resumir", lambda turnos: f"Resumen de {len(turnos)} turnos")
    bloques.registrar_mensaje("sesion", "Pregunta 3", "Respuesta 3")
    assert bloques.obtener_bloques("sesion") == ["Resumen de 3 turnos"]


def test_bloques_vencidos_se_eliminan(monkeypatch) -> None:
    monkeypatch.setattr(bloques, "_TTL", 10)
    bloques._CACHE["sesion"] = {
        "contador": 0,
        "pendientes": [],
        "bloques": ["antiguo"],
        "updated_at": (datetime.now(UTC) - timedelta(seconds=11)).isoformat(),
    }

    assert bloques.obtener_bloques("sesion") == []
