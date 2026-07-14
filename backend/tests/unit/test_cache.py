"""Auditoría de hits, misses y vencimiento de la caché de consultas."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from agente_ciar.cache import consultas


def test_guardar_y_buscar_resultado_completo() -> None:
    consultas.guardar("cuantas carreras", [], "MATCH ...", [{"total": 14}], "Hay 14.")

    hit = consultas.buscar("  CUANTAS   CARRERAS ", [])

    assert hit == {"cypher": "MATCH ...", "filas": [{"total": 14}], "respuesta": "Hay 14."}
    assert consultas.buscar("otra pregunta", []) is None


def test_entrada_vencida_se_elimina(monkeypatch) -> None:
    monkeypatch.setattr(consultas, "_TTL", 10)
    consultas.guardar("pregunta", [], "MATCH ...", [], "Sin datos.")
    clave = consultas._clave("pregunta", [])
    consultas._CACHE[clave]["creado_en"] = (datetime.now(UTC) - timedelta(seconds=11)).isoformat()

    assert consultas.buscar("pregunta", []) is None


def test_cache_acota_entradas_y_limpia_vencidas(monkeypatch) -> None:
    monkeypatch.setattr(consultas, "_MAX_ENTRADAS", 2)
    consultas.guardar("uno", [], "MATCH 1", [], "uno")
    consultas.guardar("dos", [], "MATCH 2", [], "dos")
    consultas.guardar("tres", [], "MATCH 3", [], "tres")

    assert len(consultas._CACHE) == 2
    assert consultas.buscar("uno", []) is None

    clave = consultas._clave("dos", [])
    consultas._CACHE[clave]["creado_en"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    consultas.guardar("cuatro", [], "MATCH 4", [], "cuatro")
    assert clave not in consultas._CACHE
