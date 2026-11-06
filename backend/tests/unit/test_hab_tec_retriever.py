"""Pruebas del recuperador vectorial de HAB_TEC y su integración laboral."""

from __future__ import annotations

from agente.normalizador.empleabilidad.hab_tec_retriever import (
    HabTecMatch,
    HabTecRetriever,
    _Documento,
)


def test_recuperador_filtra_por_carrera_y_aplica_top_k(monkeypatch) -> None:
    recuperador = HabTecRetriever(
        (
            _Documento("HAB_1", "Marketing", "Analítica", "Datos", (1.0, 0.0)),
            _Documento("HAB_2", "Marketing", "Campañas", "Marketing", (0.8, 0.6)),
            _Documento("HAB_3", "Arquitectura", "Planos", "Diseño", (1.0, 0.0)),
        ),
        endpoint="http://unused",
        modelo="unused",
        similitud_minima=0.5,
        limite=1,
    )
    consultas: list[str] = []

    def embedding(self, texto):
        consultas.append(texto)
        return (1.0, 0.0)

    monkeypatch.setattr(HabTecRetriever, "_embedding", embedding)

    encontrados = recuperador.buscar("analizar campañas", "marketing")

    assert encontrados == (
        HabTecMatch("HAB_1", "Marketing", "Analítica", "Datos", 1.0),
    )
    compuesto = recuperador.buscar("analizar campañas", "Marketing, Arquitectura")
    assert compuesto[0].id_habilidad == "HAB_1"
    assert recuperador.buscar("analizar campañas", "") == ()
    assert recuperador.buscar("analizar campañas", "Carrera inexistente") == ()
    assert consultas == ["analizar campañas", "analizar campañas"]
    todos = recuperador.buscar("analizar campañas", "Marketing", sin_limite=True)
    assert [c.id_habilidad for c in todos] == ["HAB_1", "HAB_2"]
    assert recuperador.buscar("   ", "Marketing") == ()
    assert consultas == ["analizar campañas"] * 3
