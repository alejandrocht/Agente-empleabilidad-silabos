"""Formato determinista de las respuestas respaldadas por tablas."""

from agente.nodos.analiza_resultado import _redactar_determinista


def test_redactor_resume_tablas_sin_repetir_cada_fila() -> None:
    respuesta = _redactar_determinista(
        [
            {"herramienta": "SAP", "ofertas": 1553},
            {"herramienta": "Microsoft Excel", "ofertas": 1318},
        ]
    )

    assert respuesta == "Se encontraron 2 herramientas. Revisa el detalle en la tabla."
    assert "SAP" not in respuesta


def test_redactor_conserva_una_respuesta_breve_para_totales() -> None:
    assert _redactar_determinista([{"total": 14}]) == "El total es 14."
