"""HTTP contract tests for technical HITL switch events."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agente.api import normalizador, servidor
from agente.normalizador.ejecuciones import GestorEjecuciones


def _cliente_con_eventos(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, peer: tuple[str, int]
) -> tuple[TestClient, list[tuple[tuple[Any, ...], dict[str, Any]]]]:
    gestor = GestorEjecuciones(tmp_path)
    eventos: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    monkeypatch.setattr(normalizador, "gestor_ejecuciones", gestor)
    monkeypatch.setattr(
        normalizador,
        "log_paso",
        lambda *args, **kwargs: eventos.append((args, kwargs)),
        raising=False,
    )
    return TestClient(servidor.app, client=peer), eventos


@pytest.mark.parametrize(
    ("hitl", "modo"),
    [
        (0, "aprobacion_automatica"),
        (1, "revision_humana"),
    ],
)
def test_registra_cambio_hitl_sin_crear_ejecucion(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    hitl: int,
    modo: str,
) -> None:
    cliente, eventos = _cliente_con_eventos(monkeypatch, tmp_path, peer=("127.0.0.1", 0))

    respuesta = cliente.post("/normalizador/eventos/hitl", json={"hitl": hitl})

    assert respuesta.status_code == 204
    assert respuesta.content == b""
    assert eventos == [
        (
            ("normalizador", "hitl_cambiado"),
            {"data": {"hitl": str(hitl), "modo": modo}},
        )
    ]
    assert list(tmp_path.iterdir()) == []


def test_rechaza_hitl_invalido_sin_emitir_evento_ni_crear_ejecucion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cliente, eventos = _cliente_con_eventos(monkeypatch, tmp_path, peer=("127.0.0.1", 0))

    respuesta = cliente.post("/normalizador/eventos/hitl", json={"hitl": 2})

    assert respuesta.status_code == 422
    assert eventos == []
    assert list(tmp_path.iterdir()) == []


def test_rechaza_peer_remoto_sin_emitir_evento_ni_crear_ejecucion(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cliente, eventos = _cliente_con_eventos(monkeypatch, tmp_path, peer=("203.0.113.10", 0))

    respuesta = cliente.post(
        "/normalizador/eventos/hitl",
        json={"hitl": 1},
        headers={
            "host": "127.0.0.1",
            "x-forwarded-for": "127.0.0.1",
            "forwarded": "for=127.0.0.1",
            "x-real-ip": "127.0.0.1",
        },
    )

    assert respuesta.status_code == 403
    assert eventos == []
    assert list(tmp_path.iterdir()) == []
